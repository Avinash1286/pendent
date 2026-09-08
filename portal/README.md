# AURA Notes

A calm, personal notes portal built with Next.js 16, React 19 and Convex. It stores transcripts, summaries, editable next steps, tags and personal context. The companion can upload a completed transcript using a separate add-only token. Audio stays on the companion unless you move it yourself.

## Run locally

Requires Node.js 22 or newer. From `portal/`:

```sh
npm ci
npx convex dev --once
npm run setup:local
npx convex dev --once
npm run dev
```

Keep `npx convex dev` running during development. The official Convex CLI starts a real local backend when no cloud deployment is configured. The setup helper adds the Next.js public URLs and generates local signing keys without printing them. `.env.local` and `.convex/` contain secrets and local data and are ignored by Git.

Open http://127.0.0.1:3000, choose **Create an account**, and use a password with at least 12 characters. Password authentication is implemented with Convex Auth. Email verification and recovery are not configured in this development release; use a password manager. No verification emails are sent.

## Capture → note → any AI

1. Record on the pendant, stop capture, and use the Python companion to sync and transcribe locally.
2. In **Connections**, create a device ingestion token. By default, uploaded notes stay out of live AI context. You can explicitly enable future synced notes when creating the token.
3. Configure the companion with the Convex **HTTP site URL**, not the `.convex.cloud` query URL, and the ingestion token. See [`../companion/README.md`](../companion/README.md).
4. In **About you**, add goals, useful background and response preferences.
5. Select notes and open **Context Pack**. Review the exact Markdown, then copy or download it for ChatGPT, Claude, Gemini, Grok, or another chat.

The provider buttons open the provider only. They do not transmit notes. Copy/paste and file attachment make the pack portable without relying on undocumented provider prefill URLs, browser extensions or API credentials.

For live access, a compatible MCP client can call the read-only `get_aura_context` tool. The endpoint is `${CONVEX_SITE_URL}/mcp`, with `Authorization: Bearer <context token>`. It exposes your profile and up to 20 recent unarchived notes explicitly enabled for context. A device ingestion token cannot read this endpoint. Tokens expire after 90 days and can be revoked.

This release implements stateless JSON responses over Streamable HTTP, protocol `2025-03-26`. It supports `initialize`, `ping`, `tools/list`, and `tools/call`; no sessions, SSE, OAuth discovery, or server-initiated messages. Clients requiring OAuth cannot connect directly. Use the portable Context Pack there.

```json
{
  "mcpServers": {
    "aura": {
      "url": "https://YOUR-DEPLOYMENT.convex.site/mcp",
      "headers": { "Authorization": "Bearer YOUR_CONTEXT_TOKEN" }
    }
  }
}
```

Client configuration syntax varies; the example describes the URL/header contract, not a universal settings format. Treat the token as a password. Captured text is labeled source data in every pack, with explicit attribution and truncation markers; this is not a guarantee against prompt injection in a downstream model.

## Backend contracts

- `POST /api/ingest`: bearer ingestion token; JSON `title`, `transcript`, `summary[]`, `actions[]`, `tags[]`, `recordedAt` (Unix milliseconds), plus either legacy `sourceId` or the new `capture` metadata object. Returns `{id, stored:true}`. Legacy v1 retries remain token/source scoped. V2 capture imports deduplicate by authenticated owner + device ID + capture ID across token rotation, preserve the original transcript/segments and reject conflicting source replays with HTTP 409. [Exact provenance schema and compatibility limits](../docs/a04/portal-provenance.md).
- `GET /api/context`: bearer context token; returns `{markdown, noteCount, generatedAt}`.
- `POST /mcp`: bearer context token; JSON-RPC 2.0.

HTTP bodies are limited to 256 KiB; transcripts to 60,000 characters, titles to 160, summaries to 20 lines, next steps to 30 lines, and tags to 10. The current library view loads the latest 200 notes (search returns up to 100). Context packs include at most 30 selected notes, 6,000 transcript characters each, and 45,000 total characters, with visible truncation markers. Original saved transcripts remain unchanged.

Every user-facing query/mutation derives its owner from the authenticated Convex identity. Token secrets are shown once and stored only as SHA-256 hashes in the database. Ingestion is idempotent within a token; rotating the token changes the source namespace. Archiving hides a note from live context immediately and is reversible. This release does not implement account deletion, password recovery, audio cloud storage or end-to-end encryption.

## Verification

```sh
npm test
npm run typecheck
npm run build
node scripts/verify-local.mjs
node scripts/verify-auth-proxy.mjs
```

Eleven unit tests exercise cross-account access, sharing consent, token permissions, revocation, expiration, HTTP validation, context truncation and lossless JSON import. The integration script refuses non-loopback backends, creates two synthetic password accounts on real local Convex, tests storage/HTTP/MCP, revokes tokens, archives test notes and signs out. The auth-proxy script needs `npm run dev` on port 3000 and checks Next.js origin/action restrictions, HttpOnly refresh cookies, renewal and logout. Neither evidence file contains credentials.

## Vercel + Convex production

The Vercel project is `pendent-notes`. No GitHub Actions are used. Convex's free integration setup is pending account terms acceptance; a local database is not a production cloud database.

Once the integration is provisioned, configure `CONVEX_DEPLOY_KEY`, `NEXT_PUBLIC_CONVEX_URL`, and `NEXT_PUBLIC_CONVEX_SITE_URL` for the production deployment. Generate distinct production `JWT_PRIVATE_KEY` and `JWKS` values in Convex, and set `SITE_URL` to the final Vercel portal URL. Never reuse local signing keys. Deploy Convex functions before deploying the Next.js frontend. Keep the key server-side; only the two public URLs belong in `NEXT_PUBLIC_*`.

Vercel build command can be `npx convex deploy --cmd 'npm run build'` with the deployment key configured. Deploy from `portal/`, linked to `pendent-notes`; the product showcase uses a separate `pendent` project with `website/` as its root directory. `vercel.json` disables automatic Git deployments so releases are explicit CLI deployments.

References: [Convex local deployments](https://docs.convex.dev/cli/local-deployments), [Convex Auth manual setup](https://labs.convex.dev/auth/setup/manual), [Next.js authorization](https://labs.convex.dev/auth/authz/nextjs), [Convex tests](https://docs.convex.dev/testing/convex-test).
