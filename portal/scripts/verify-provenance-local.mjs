import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { isDeepStrictEqual } from "node:util";
import { ConvexHttpClient } from "convex/browser";
import { api } from "../convex/_generated/api.js";

// Synthetic local-only integration. Secrets stay in memory/environment and never enter evidence.
const origin = process.env.AURA_VERIFY_ORIGIN ?? "http://127.0.0.1:3000";
const backend = process.env.AURA_VERIFY_CONVEX_URL ?? "http://127.0.0.1:3210";
const site = process.env.AURA_VERIFY_CONVEX_SITE_URL ?? "http://127.0.0.1:3211";
for (const address of [origin, backend, site])
  assert.match(
    address,
    /^http:\/\/127\.0\.0\.1:\d+$/,
    "Only explicit loopback servers are supported",
  );
assert.equal(
  process.env.AURA_VERIFY_SYNTHETIC,
  "1",
  "Confirm the supplied note is a synthetic fixture",
);
assert.ok(process.env.AURA_VERIFY_NOTE, "Supply a generated synthetic AUR3 note path");
const notePath = resolve(process.env.AURA_VERIFY_NOTE);
const noteBytes = readFileSync(notePath);
const note = JSON.parse(noteBytes);
assert.equal(note.capture?.version, 2, "A generated provenance note is required");
const checks = [];
const accounts = [];
let stage = "starting";
let status = "FAIL";
const pass = (label) => {
  checks.push(label);
  console.log(`PASS ${label}`);
};
const requireThat = (condition) => assert.ok(condition, `Local smoke stage failed: ${stage}`);
async function authPost(body, cookie) {
  return fetch(`${origin}/api/auth`, {
    method: "POST",
    redirect: "error",
    headers: {
      "Content-Type": "application/json",
      Origin: origin,
      ...(cookie ? { Cookie: cookie } : {}),
    },
    body: JSON.stringify(body),
  });
}
async function account() {
  const response = await authPost({
    action: "auth:signIn",
    args: {
      provider: "password",
      params: {
        flow: "signUp",
        email: `aura-source-${randomBytes(8).toString("hex")}@example.invalid`,
        password: randomBytes(24).toString("base64url"),
      },
    },
  });
  requireThat(response.status === 200);
  const body = await response.json();
  requireThat(typeof body.tokens?.token === "string" && body.tokens.refreshToken === "dummy");
  const client = new ConvexHttpClient(backend);
  client.setAuth(body.tokens.token);
  const record = {
    client,
    cookie: response.headers
      .getSetCookie()
      .map((value) => value.split(";", 1)[0])
      .join("; "),
    tokens: [],
    notes: [],
  };
  accounts.push(record);
  return record;
}
async function token(owner, scope = "ingest", autoContext = false) {
  const value = await owner.client.action(api.tokenActions.create, {
    name: "Synthetic A04 provenance verification",
    scope,
    autoContext,
  });
  owner.tokens.push(value.id);
  return value;
}
function upload(secret) {
  // Exercise the actual Python upload module and its source-sidecar checks.
  const code =
    "import json,sys; from pathlib import Path; from aura_companion.upload import upload_note; print(json.dumps(upload_note(Path(sys.argv[1]))))";
  const result = execFileSync(process.env.AURA_VERIFY_PYTHON ?? "python", ["-c", code, notePath], {
    env: {
      ...process.env,
      PYTHONPATH: resolve("../companion/src"),
      AURA_PORTAL_URL: site,
      AURA_INGEST_TOKEN: secret,
    },
    encoding: "utf8",
    timeout: 60000,
    stdio: ["ignore", "pipe", "pipe"],
  });
  return JSON.parse(result);
}
const rawPayload = {
  title: note.title,
  transcript: note.transcript,
  summary: note.summary,
  actions: note.suggested_actions ?? note.actions ?? [],
  tags: note.tags ?? [],
  recordedAt: note.recordedAt,
  capture: note.capture,
};
async function post(secret, data = rawPayload) {
  return fetch(`${site}/api/ingest`, {
    method: "POST",
    redirect: "error",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${secret}`,
    },
    body: JSON.stringify(data),
  });
}

try {
  stage = "Next.js signup and owner authentication";
  const alice = await account();
  const bob = await account();
  pass(stage);
  stage = "Python AUR3 note upload into real local Convex";
  const first = await token(alice);
  const receipt = upload(first.secret);
  requireThat(receipt.stored === true && typeof receipt.id === "string");
  alice.notes.push(receipt.id);
  let stored = (await alice.client.query(api.notes.list, {})).find(
    (value) => value._id === receipt.id,
  );
  requireThat(
    stored?.sourceTranscript === note.transcript && isDeepStrictEqual(stored.capture, note.capture),
  );
  requireThat(stored.contextEnabled === false);
  pass(stage);
  stage = "Rotated token reuses source and preserves consent";
  await alice.client.mutation(api.tokens.revoke, { id: first.id });
  const rotated = await token(alice, "ingest", true);
  requireThat(upload(rotated.secret).id === receipt.id);
  requireThat((await alice.client.query(api.notes.list, {})).length === 1);
  requireThat((await post(first.secret)).status === 401);
  pass(stage);
  stage = "Owner boundary for identical declared capture";
  requireThat((await bob.client.query(api.notes.list, {})).length === 0);
  const bobToken = await token(bob);
  const bobReceipt = upload(bobToken.secret);
  requireThat(bobReceipt.id !== receipt.id);
  bob.notes.push(bobReceipt.id);
  pass(stage);
  stage = "Source conflict preserves original";
  const conflict = await post(rotated.secret, {
    ...rawPayload,
    capture: { ...note.capture, archiveDigest: "00".repeat(32) },
  });
  requireThat(conflict.status === 409);
  pass(stage);
  stage = "Owner edits retain immutable source";
  await alice.client.mutation(api.notes.save, {
    ...rawPayload,
    capture: undefined,
    id: receipt.id,
    transcript: "Synthetic owner correction for source preservation verification.",
    contextEnabled: false,
  });
  requireThat(upload(rotated.secret).id === receipt.id);
  stored = (await alice.client.query(api.notes.list, {})).find((value) => value._id === receipt.id);
  requireThat(stored.sourceTranscript === note.transcript && stored.transcript !== note.transcript);
  pass(stage);
  stage = "Consent-controlled live context retains source revision";
  const contextToken = await token(alice, "context");
  const contextRequest = () =>
    fetch(`${site}/api/context`, {
      headers: { Authorization: `Bearer ${contextToken.secret}` },
      redirect: "error",
    });
  requireThat((await (await contextRequest()).json()).noteCount === 0);
  await alice.client.mutation(api.notes.toggleContext, { id: receipt.id, enabled: true });
  const context = await (await contextRequest()).json();
  requireThat(
    context.noteCount === 1 && context.markdown.includes(note.capture.transcriptRevision),
  );
  requireThat(
    context.markdown.includes("Owner-edited note") &&
      context.markdown.includes(note.capture.captureId),
  );
  if (note.capture.timeConfidence === "unknown")
    requireThat(context.markdown.includes("Unknown (not upload time)"));
  pass(stage);
  status = "PASS";
} catch {
  console.error(`FAIL ${stage}; private response bodies and credentials were suppressed`);
  process.exitCode = 1;
} finally {
  let cleaned = true;
  for (const owner of accounts) {
    for (const id of owner.notes)
      try {
        await owner.client.mutation(api.notes.archive, { id, archived: true });
      } catch {
        cleaned = false;
      }
    for (const id of owner.tokens)
      try {
        await owner.client.mutation(api.tokens.revoke, { id });
      } catch {
        cleaned = false;
      }
    try {
      if ((await authPost({ action: "auth:signOut", args: {} }, owner.cookie)).status !== 200)
        cleaned = false;
    } catch {
      cleaned = false;
    }
  }
  if (cleaned) pass("Synthetic notes archived, tokens revoked and sessions signed out");
  else {
    status = "FAIL";
    process.exitCode = 1;
    console.error("FAIL synthetic cleanup; inspect local test records");
  }
  const evidencePath = "verification/a04-provenance-local.json";
  mkdirSync(dirname(evidencePath), { recursive: true });
  writeFileSync(
    evidencePath,
    JSON.stringify(
      {
        testedAt: new Date().toISOString(),
        status,
        origin,
        backend,
        site,
        sourceNoteSha256: createHash("sha256").update(noteBytes).digest("hex"),
        checks,
        limitations:
          "Synthetic HTTP integration against real local Next.js and Convex, using the Python uploader. No browser interaction, cloud deployment, physical BLE transfer or authenticated-device proof. Synthetic account records remain only in ignored local data; their tokens are revoked and notes archived.",
      },
      null,
      2,
    ) + "\n",
  );
}
