/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { expect, test } from "vitest";
import schema from "../convex/schema";
import { api, internal } from "../convex/_generated/api";
import type { Id } from "../convex/_generated/dataModel";
import { parseCapture, transcriptDigest, type Capture } from "../lib/capture";
import { buildContext } from "../lib/context";
import { parseImportedNote } from "../lib/import-note";

const modules = import.meta.glob("../convex/**/*.ts");
const original = {
  title: "A small idea",
  transcript: "A quieter chain.",
  summary: ["Try a quieter chain."],
  actions: [],
  tags: [],
  recordedAt: 0,
  contextEnabled: false,
};
async function capture(): Promise<Capture> {
  return {
    version: 2,
    deviceId: "11".repeat(16),
    captureId: "22".repeat(16),
    archiveDigest: "33".repeat(32),
    sampleRate: 16000,
    sourceSamples: 32000,
    startedAtMs: 0,
    timeConfidence: "unknown",
    interrupted: false,
    bookmarks: [8000],
    transcriptRevision: await transcriptDigest(original.transcript),
    segments: [{ start: 0.1, end: 1.2, text: original.transcript }],
    transcription: { engine: "faster-whisper", model: "tiny.en", version: "test-fixture" },
  };
}
async function fixture() {
  const t = convexTest(schema, modules);
  const [aliceId, bobId] = await t.run(async (ctx) => [
    await ctx.db.insert("users", { name: "Alice" }),
    await ctx.db.insert("users", { name: "Bob" }),
  ]);
  let tokenCount = 0;
  async function token(ownerId: Id<"users">, autoContext = false) {
    const secret = `aura_ingest_${String.fromCharCode(97 + tokenCount++).repeat(43)}`;
    const id = await t.mutation(internal.tokens.insert, {
      ownerId,
      name: "Test fixture",
      hash: await transcriptDigest(secret),
      prefix: secret.slice(0, 20),
      scope: "ingest",
      autoContext,
    });
    return { id, secret };
  }
  const first = await token(aliceId);
  return {
    t,
    aliceId,
    bobId,
    token,
    first,
    alice: t.withIdentity({ subject: `${aliceId}|session` }),
  };
}

test("a capture deduplicates across rotated tokens, retaining owner edits, archive and sharing state", async () => {
  const { t, alice, aliceId, first, token } = await fixture();
  const payload = { ...original, capture: await capture() };
  const id = await t.mutation(internal.notes.ingest, { ...payload, tokenId: first.id });
  await alice.mutation(api.notes.save, {
    ...original,
    id,
    transcript: "My later interpretation.",
    title: "Edited",
    summary: [],
    contextEnabled: true,
  });
  await alice.mutation(api.notes.archive, { id, archived: true });
  await alice.mutation(api.tokens.revoke, { id: first.id });
  const rotated = await token(aliceId, false);
  expect(
    await t.mutation(internal.notes.ingest, {
      ...payload,
      title: "A regenerated title",
      summary: ["New derived draft"],
      tokenId: rotated.id,
    }),
  ).toBe(id);
  const stored = await t.run((ctx) => ctx.db.get(id));
  expect(stored).toMatchObject({
    title: "Edited",
    transcript: "My later interpretation.",
    sourceTranscript: original.transcript,
    contextEnabled: true,
    archived: true,
    capture: payload.capture,
  });
  expect(await t.run((ctx) => ctx.db.query("notes").collect())).toHaveLength(1);
  await alice.mutation(api.notes.archive, { id, archived: false });
  expect(
    (await alice.query(api.notes.list, { search: "quieter" })).map((value) => value._id),
  ).toEqual([id]);
});

test("new unknown-time captures remain in recent views after more than 200 dated imports", async () => {
  const { t, alice, aliceId, token } = await fixture();
  await t.run(async (ctx) => {
    for (let index = 0; index < 205; index++)
      await ctx.db.insert("notes", {
        ...original,
        ownerId: aliceId,
        recordedAt: 100000 + index,
        updatedAt: 100000,
        source: "portal",
        archived: false,
        contextEnabled: true,
        searchText: "older dated source",
      });
  });
  const permission = await token(aliceId, true);
  const id = await t.mutation(internal.notes.ingest, {
    ...original,
    capture: await capture(),
    tokenId: permission.id,
  });
  const recent = await alice.query(api.notes.list, {});
  expect(recent).toHaveLength(200);
  expect(recent[0]).toMatchObject({ _id: id, recordedAt: 0 });
  const live = await t.query(internal.notes.liveContext, { ownerId: aliceId });
  expect(live.notes).toHaveLength(20);
  expect(live.notes[0]._id).toBe(id);
});

test("the same declared device/capture under another owner is a separate private record", async () => {
  const { t, alice, bobId, first, token } = await fixture();
  const bobToken = await token(bobId);
  const payload = { ...original, capture: await capture() };
  const aliceNote = await t.mutation(internal.notes.ingest, { ...payload, tokenId: first.id });
  const bobNote = await t.mutation(internal.notes.ingest, { ...payload, tokenId: bobToken.id });
  expect(aliceNote).not.toBe(bobNote);
  expect((await alice.query(api.notes.list, {})).map((note) => note._id)).toEqual([aliceNote]);
  await expect(alice.mutation(api.notes.save, { ...original, id: bobNote })).rejects.toThrow();
});

test("different devices and different captures never merge even with identical transcripts", async () => {
  const { t, first } = await fixture();
  const source = await capture();
  const ids = [];
  for (const metadata of [
    source,
    { ...source, deviceId: "44".repeat(16) },
    { ...source, captureId: "55".repeat(16) },
  ])
    ids.push(
      await t.mutation(internal.notes.ingest, {
        ...original,
        capture: metadata,
        tokenId: first.id,
      }),
    );
  expect(new Set(ids).size).toBe(3);
});

test("simultaneous first imports using two tokens resolve to one owner/capture", async () => {
  const { t, first, token, aliceId } = await fixture();
  const next = await token(aliceId);
  const payload = { ...original, capture: await capture() };
  const [a, b] = await Promise.all(
    [first, next].map(({ id }) => t.mutation(internal.notes.ingest, { ...payload, tokenId: id })),
  );
  expect(a).toBe(b);
});

test("conflicting audio revision, time confidence, duration, segment or model cannot replace a source", async () => {
  const { t, first } = await fixture();
  const source = await capture();
  const payload = { ...original, capture: source, tokenId: first.id };
  const id = await t.mutation(internal.notes.ingest, payload);
  for (const changed of [
    { ...source, archiveDigest: "44".repeat(32) },
    { ...source, startedAtMs: 100000, timeConfidence: "host_synced" as const },
    { ...source, sourceSamples: 32100 },
    { ...source, segments: [{ ...source.segments[0], end: 1.3 }] },
    { ...source, transcription: { ...source.transcription, model: "small.en" } },
    { ...source, interrupted: true },
    { ...source, bookmarks: [9000] },
  ])
    await expect(
      t.mutation(internal.notes.ingest, {
        ...payload,
        capture: changed,
        recordedAt: changed.startedAtMs,
      }),
    ).rejects.toThrow(/SOURCE_CONFLICT/);
  const changedText = "An unrelated source.";
  await expect(
    t.mutation(internal.notes.ingest, {
      ...payload,
      transcript: changedText,
      capture: { ...source, transcriptRevision: await transcriptDigest(changedText) },
    }),
  ).rejects.toThrow(/SOURCE_CONFLICT/);
  expect((await t.run((ctx) => ctx.db.get(id)))?.sourceTranscript).toBe(original.transcript);
});

test("bad transcript digest is rejected before storage and Unicode bytes are exact", async () => {
  const { t, first } = await fixture();
  await expect(
    t.mutation(internal.notes.ingest, {
      ...original,
      capture: { ...(await capture()), transcriptRevision: "00".repeat(32) },
      tokenId: first.id,
    }),
  ).rejects.toThrow(/INVALID_SOURCE/);
  expect(await t.run((ctx) => ctx.db.query("notes").collect())).toHaveLength(0);
  expect(await transcriptDigest("é")).not.toBe(await transcriptDigest("e\u0301"));
  await expect(transcriptDigest("bad\ud800text")).rejects.toThrow();
  await expect(transcriptDigest("bad\udc00text")).rejects.toThrow();
  expect(await transcriptDigest("A necklace 💡")).toMatch(/^[0-9a-f]{64}$/);
});

test("revoked and exactly expired tokens cannot replay an already stored capture", async () => {
  const { t, first, token, aliceId } = await fixture();
  const payload = { ...original, capture: await capture() };
  await t.mutation(internal.notes.ingest, { ...payload, tokenId: first.id });
  await t.run((ctx) => ctx.db.patch(first.id, { revoked: true }));
  await expect(
    t.mutation(internal.notes.ingest, { ...payload, tokenId: first.id }),
  ).rejects.toThrow(/UNAUTHORIZED/);
  const expired = await token(aliceId);
  await t.run((ctx) => ctx.db.patch(expired.id, { expiresAt: Date.now() }));
  await expect(
    t.mutation(internal.notes.ingest, { ...payload, tokenId: expired.id }),
  ).rejects.toThrow(/UNAUTHORIZED/);
});

test("v2 HTTP preserves source metadata, returns conflict and excludes unauthorized reads", async () => {
  const { t, first, alice, aliceId, token } = await fixture();
  const payload = { ...original, capture: await capture() };
  const post = (secret: string, body = payload) =>
    t.fetch("/api/ingest", {
      method: "POST",
      headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  const response = await post(first.secret);
  expect(response.status).toBe(200);
  const { id } = await response.json();
  const second = await token(aliceId, true);
  expect((await (await post(second.secret)).json()).id).toBe(id);
  expect((await alice.query(api.notes.list, {}))[0]).toMatchObject({
    capture: payload.capture,
    sourceTranscript: original.transcript,
    contextEnabled: false,
  });
  expect(
    (
      await post(second.secret, {
        ...payload,
        capture: { ...payload.capture, archiveDigest: "55".repeat(32) },
      })
    ).status,
  ).toBe(409);
  await t.run((ctx) => ctx.db.patch(second.id, { revoked: true }));
  expect((await post(second.secret)).status).toBe(401);
  expect(
    (await t.fetch("/api/context", { headers: { Authorization: `Bearer ${first.secret}` } }))
      .status,
  ).toBe(401);
});

test("legacy notes remain token scoped and are never inferred to be the v2 source", async () => {
  const { t, first, token, aliceId } = await fixture();
  const legacy = { ...original, sourceId: "old-recording" };
  const a = await t.mutation(internal.notes.ingest, { ...legacy, tokenId: first.id });
  const second = await token(aliceId);
  const b = await t.mutation(internal.notes.ingest, { ...legacy, tokenId: second.id });
  const c = await t.mutation(internal.notes.ingest, {
    ...legacy,
    capture: await capture(),
    tokenId: second.id,
  });
  expect(new Set([a, b, c]).size).toBe(3);
  expect((await t.run((ctx) => ctx.db.get(a)))?.capture).toBeUndefined();
});

test("manual import retains v2 time and segments, requires fresh consent and shares owner dedup", async () => {
  const { t, alice, first } = await fixture();
  const payload = { ...original, capture: await capture(), contextEnabled: true };
  const imported = parseImportedNote(payload, 123456789);
  expect(imported).toMatchObject({
    recordedAt: 0,
    capture: payload.capture,
    contextEnabled: false,
  });
  const id = await alice.mutation(api.notes.save, imported);
  expect(await t.mutation(internal.notes.ingest, { ...payload, tokenId: first.id })).toBe(id);
  await expect(
    alice.mutation(api.notes.save, { ...original, id, capture: payload.capture }),
  ).rejects.toThrow(/cannot be edited/);
  expect(() => parseImportedNote({ ...payload, recordedAt: undefined }, 123456789)).toThrow();
});

test("source bounds reject unsafe, mismatched and unbounded timing without dropping fields", async () => {
  const source = await capture();
  for (const changed of [
    { ...source, deviceId: "00".repeat(16) },
    { ...source, deviceId: "AA".repeat(16) },
    { ...source, startedAtMs: 100, timeConfidence: "unknown" },
    { ...source, sourceSamples: 320000001 },
    { ...source, sourceSamples: 1.5 },
    { ...source, bookmarks: [9000, 8000] },
    { ...source, bookmarks: [32001] },
    { ...source, segments: [{ start: 1, end: 3, text: "past duration" }] },
    {
      ...source,
      segments: [
        { start: 0, end: 1, text: "a" },
        { start: 0.9, end: 1.1, text: "overlap" },
      ],
    },
    { ...source, segments: [{ start: 0, end: NaN, text: "invalid" }] },
    { ...source, segments: Array(2001).fill({ start: 0, end: 0, text: "" }) },
    { ...source, unexpected: true },
  ])
    expect(() => parseCapture(changed, changed.startedAtMs)).toThrow();
  expect(() => parseCapture(source, 1)).toThrow();
});

test("interrupted bookmarks beyond decoded audio are retained and clearly unavailable", async () => {
  const source = { ...(await capture()), interrupted: true, bookmarks: [8000, 64000] };
  expect(parseCapture(source, 0).bookmarks).toEqual([8000, 64000]);
  expect(() => parseCapture({ ...source, bookmarks: [320000001] }, 0)).toThrow();
  const pack = buildContext(null, [
    {
      ...original,
      capture: source,
      sourceTranscript: original.transcript,
      transcript: "An owner's correction.",
    },
  ]);
  expect(pack).toContain("Captured: Unknown (not upload time)");
  expect(pack).not.toContain("1970-");
  expect(pack).toContain("[0.100–1.200s] A quieter chain.");
  expect(pack).toContain("4.000s (audio unavailable in recovered prefix)");
  expect(pack).toContain("Owner-edited note (distinct from captured source)");
  expect(pack).toContain(source.archiveDigest);
  expect(pack).toContain(source.transcriptRevision);
  expect(pack).not.toContain(source.deviceId);
});
