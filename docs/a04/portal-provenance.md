# A04 portal capture provenance

Status: implemented in the local Next.js/Convex source and exercised with Convex HTTP/mutation tests. No cloud deployment, account terms acceptance, physical pairing or authenticated-device protocol was performed. This work retains source material during portal ingestion; it does not prove that a sender's device or audio archive is authentic.

## Public upload contract

Use the existing `POST /api/ingest` with `Authorization: Bearer <ingest token>`. The base fields remain `title`, `transcript`, `summary[]`, `actions[]`, `tags[]` and `recordedAt`. Add this `capture` object for stable provenance:

```json
{
  "version": 2,
  "deviceId": "11111111111111111111111111111111",
  "captureId": "22222222222222222222222222222222",
  "archiveDigest": "3333333333333333333333333333333333333333333333333333333333333333",
  "sampleRate": 16000,
  "sourceSamples": 32000,
  "startedAtMs": 0,
  "timeConfidence": "unknown",
  "interrupted": false,
  "bookmarks": [8000],
  "transcriptRevision": "<64 lowercase hex SHA-256 of the exact UTF-8 transcript>",
  "segments": [{ "start": 0.1, "end": 1.2, "text": "A quieter chain." }],
  "transcription": { "engine": "faster-whisper", "model": "tiny.en", "version": "<installed version>" }
}
```

This is a structural example, not a valid digest-bearing fixture. The public **capture metadata version 2** is separate from the companion archive's experimental binary protocol version. An archive update to wire version 3 does not change this metadata object. `archiveDigest` denotes the archive receipt's final chain digest, including its terminal metadata when that wire version provides a seal; it is not the SHA-256 of an arbitrary `.sqlite`, JSON or Opus file. The portal preserves this sender declaration and cannot recompute it without the source archive.

`transcriptRevision` is SHA-256 over the transcript's exact UTF-8 bytes, with no Unicode normalization, whitespace change, newline rewrite or JSON wrapper. The server independently recomputes it and rejects lone Unicode surrogates rather than hashing replacement characters. Segment times use seconds and bookmarks use source sample offsets. `recordedAt` must exactly equal `startedAtMs`; unknown time uses `0` plus `timeConfidence: "unknown"`, and stays unknown in the interface and Context Pack. Host-synchronized time requires a positive epoch millisecond value; it is a sender claim about clock origin, not a measured accuracy guarantee.

Limits are checked without truncation:

| Field | Bound |
|---|---|
| IDs | Nonzero 128-bit IDs, exactly 32 lowercase hex characters each |
| Digests | Exactly 64 lowercase hex characters |
| Source samples | Integer 0–320,000,000 at the declared 16,000 Hz |
| Capture time | Integer 0 through server time + one day, consistent with the time-confidence field |
| Segments | At most 2,000; finite, ordered, nonoverlapping start/end within decoded source duration; each text ≤2,000 characters and combined text ≤60,000 |
| Bookmarks | At most 1,000, nondecreasing integer sample offsets; finalized captures require offsets ≤source samples |
| Interrupted bookmark tail | Offsets may exceed decoded duration, up to 320,000,000; displayed as audio unavailable, without a seek link |
| Transcription method | Required nonempty `engine`, `model`, `version`, each ≤160 characters |
| Base note / request | Existing title/transcript/summary/action/tag bounds remain; entire HTTP body ≤262,144 bytes |

String lengths use JavaScript UTF-16 code units. Invalid types, unknown capture fields and violated bounds fail the whole request. Long recordings/transcripts require deliberate session splitting or a future paginated source design; this endpoint does not silently discard excess material. There is no raw audio upload or playback service in this change.

The notes screen retrieves at most 200 notes (100 for a search), and live context at most 20 approved notes. Recent views now sort by arrival in the portal, so a newly imported capture with unknown source time cannot disappear behind hundreds of older dated notes. Source capture time is retained separately and never replaced by arrival time. These are bounded recent-note views, not complete archive search. Retaining source text/segments increases document and response size; full-size multi-note archives still need paginated source retrieval and measured backend transaction/response headroom before production use. No bulk-archive performance claim follows from the focused tests.

## Identity, retries and consent

The authenticated, unexpired, unrevoked ingestion token supplies the owner. Neither a submitted owner ID nor the device/capture pair grants access to another owner's data. The indexed key is `(ownerId, "v2:" + deviceId + ":" + captureId)`. Two valid tokens for the same owner converge on one record inside a Convex mutation transaction, even after credential rotation. The same declared pair under another owner remains a separate private record. Device identities and archive digests remain sender assertions until a future physically paired, authenticated device/session protocol supplies proof.

The first successful import retains `capture` and `sourceTranscript` as source fields. Later identical source replays return the existing ID. Changes to audio digest, source duration/time/interruption/bookmarks, transcript bytes/revision, segments or transcription engine/model/version return HTTP 409 and preserve the first source. A recovered prefix followed by a complete capture with the same identity therefore requires explicit review; this release does not overwrite or automatically merge those revisions. Local source archives must retain both revisions until that review workflow exists.

Regenerated titles, summaries, actions and tags on a replay do not replace the existing note. Owner edits, archive status and current context choice also survive retries. Initial device imports apply only the token's explicit `autoContext` setting; caller context flags cannot enable sharing. Rotating to a token with a different sharing preference cannot change an already stored note. Authentication is rechecked inside the mutation, including before an idempotent return, so revoked/expired tokens cannot use replay as a bypass.

The signed-in owner can edit the note text separately from its retained source, and can inspect/export source segments and metadata in the note dialog. Context Packs label original source and owner-edited text separately, preserve unknown/interrupted timing, and carry capture/revision attribution. Stable device IDs are intentionally omitted from Context Pack text. Only the existing owner-approved, unarchived note query feeds live context. A source export still contains personal material and identifiers, under the owner's existing explicit export action.

## Existing v1 records

All new schema fields and the capture index are additive. Old notes remain readable without migration. A request without `capture` still requires legacy `sourceId`, whose stored identity remains `tokenId:sourceId`. There is no safe inferred device ID in those records, so the system does not merge them across rotated tokens or match them to a v2 capture from filenames, transcript text or timestamps. Upgrading an old capture may create a separate v2 note. No automatic backfill, destructive cleanup, cross-owner deduplication or silent attachment of provenance to an old note occurs.

Manual JSON import accepts the same v2 metadata, requires a source recording time, and starts with sharing disabled. Saving a new captured import uses the same owner/capture deduplication rule; the immutable transcript is checked before storage. Editing source fields on an existing note is rejected. Full source-revision review, owner-approved legacy linking, correction history, device authentication, storage encryption, deletion/export lifecycle and mobile background synchronization remain separate work.

## Verification

Run from `portal/`: `npm test`, `npm run typecheck`, `npm run build`. The 24 passing tests include a focused provenance suite exercising rotated tokens, owner/device isolation, concurrent imports, conflicting source revisions, revoked/expired credentials, the Convex HTTP route, immutable/searchable source after owner edits, preserved consent/archive state, v1 compatibility, manual JSON import, interrupted bookmarks and visibility of new unknown-time captures after 200 dated notes. It uses synthetic test text and local Convex test storage, not real recordings or production credentials.

The separate [local integration evidence](../../portal/verification/a04-provenance-local.json) passes eight check groups against actual Next.js and the existing local Convex backend. The source came through the real C Opus encoder, AUR3 archive import, WAV decode and Whisper transcription; the script invokes the actual Python `upload_note`/`note_payload`, then checks token rotation, owner boundaries, source conflicts, retained source after edits and consent-controlled live context. This is HTTP integration, not a browser or physical-radio test. Synthetic notes were archived, tokens revoked and sessions signed out; synthetic account records remain only in the ignored local database.

To repeat after generating a synthetic note and starting the documented local servers:

```powershell
$env:AURA_VERIFY_SYNTHETIC = '1'
$env:AURA_VERIFY_NOTE = 'F:/path/to/generated-synthetic.note.json'
node scripts/verify-provenance-local.mjs
```

The script accepts only loopback servers. It generates disposable credentials in memory, suppresses private response/error bodies and writes only source hashes and check outcomes to evidence. Do not point it at private recordings. The portal tests, TypeScript and Next.js production build also passed for this checkpoint; no cloud terms, user credentials or cloud deployment configuration were changed.

Implementation references: [capture validator and digest](../../portal/lib/capture.ts), [transactional ingestion](../../portal/convex/notes.ts), [HTTP endpoint](../../portal/convex/http.ts), [schema](../../portal/convex/schema.ts), [tests](../../portal/tests/provenance.test.ts). Convex documents the supported [Web Crypto runtime APIs](https://docs.convex.dev/functions/runtimes) and [transactional mutation semantics](https://docs.convex.dev/understanding/overview); these support the implementation, while physical device and archive authenticity remain outside this endpoint's evidence.
