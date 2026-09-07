import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";

const origin = process.env.AURA_VERIFY_ORIGIN ?? "http://127.0.0.1:3000";
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin))
  throw new Error("Use a loopback development server for synthetic-account verification.");
const endpoint = `${origin}/api/auth`;
const evidence = [];
const check = (label) => {
  evidence.push(label);
  console.log(`PASS ${label}`);
};
const post = (body, extra = {}) =>
  fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: origin, ...extra },
    body: JSON.stringify(body),
    redirect: "error",
  });
function cookies(response) {
  const values = response.headers.getSetCookie();
  for (const value of values) {
    assert.match(value, /; HttpOnly/i);
    assert.match(value, /; SameSite=lax/i);
  }
  return values.map((value) => value.split(";", 1)[0]).join("; ");
}

assert.equal((await fetch(endpoint)).status, 405);
assert.equal((await post({ action: "notes:list", args: {} })).status, 400);
assert.equal(
  (await post({ action: "auth:signOut", args: {} }, { Origin: "https://untrusted.example" }))
    .status,
  403,
);
check("The Next.js authentication proxy rejects GET, unrelated actions and cross-origin requests");

const signup = await post({
  action: "auth:signIn",
  args: {
    provider: "password",
    params: {
      flow: "signUp",
      email: `aura-proxy-${randomBytes(8).toString("hex")}@example.invalid`,
      password: randomBytes(24).toString("base64url"),
    },
  },
});
assert.equal(signup.status, 200);
const account = await signup.json();
assert.ok(account.tokens?.token);
assert.equal(account.tokens.refreshToken, "dummy");
let cookie = cookies(signup);
assert.match(cookie, /__convexAuthRefreshToken=/);
check(
  "Password signup through Next.js returns an access token and keeps the real refresh token in HttpOnly SameSite cookies",
);

const refresh = await post(
  { action: "auth:signIn", args: { refreshToken: "dummy" } },
  { Cookie: cookie },
);
assert.equal(refresh.status, 200);
const renewed = await refresh.json();
assert.ok(renewed.tokens?.token);
assert.equal(renewed.tokens.refreshToken, "dummy");
cookie = cookies(refresh);
check("The Next.js proxy renews an authenticated session using its refresh cookie");

const signout = await post({ action: "auth:signOut", args: {} }, { Cookie: cookie });
assert.equal(signout.status, 200);
const cleared = cookies(signout);
assert.match(cleared, /__convexAuthJWT=($|;)/);
assert.match(cleared, /__convexAuthRefreshToken=($|;)/);
// Browsers remove expired cookies instead of sending empty values back.
const after = await post({ action: "auth:signIn", args: { refreshToken: "dummy" } });
assert.equal((await after.json()).tokens, null);
const revoked = await post(
  { action: "auth:signIn", args: { refreshToken: "dummy" } },
  { Cookie: cookie },
);
assert.ok(!(await revoked.json()).tokens?.token, "The old session must not renew after sign-out");
check(
  "Sign-out clears the authentication cookies and a subsequent refresh has no authenticated session",
);

mkdirSync("verification", { recursive: true });
writeFileSync(
  "verification/auth-proxy.json",
  `${JSON.stringify({ testedAt: new Date().toISOString(), origin, status: "PASS", checks: evidence, limitations: "HTTP integration against local Next.js and Convex; no browser interaction or production-domain cookie verification." }, null, 2)}\n`,
);
