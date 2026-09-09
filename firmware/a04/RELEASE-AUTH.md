# A04 RLS1 owner-release authentication primitive

`src/aura_release_auth.c` implements bounded standard HMAC-SHA256 over a canonical owner-release message, using the existing `aura_archive_sha256` implementation. It authenticates exact bytes against caller-supplied trusted context and an expected terminal ACK3. It performs no deletion, persistence, provisioning, receipt issuance or physical device communication. AUR3 and ACK3 remain unchanged.

## Wire contract

RLS1 is exactly182 bytes. Integers are unsigned little-endian; there is no C struct padding, variable field, trailing data or outer CRC.

| Offset | Bytes | Required field |
|---:|---:|---|
| 0 | 4 | `RLS1` |
| 4 | 1 | Version1 |
| 5 | 1 | Algorithm1: full HMAC-SHA256 |
| 6 | 1 | Action1: release the exact terminal capture |
| 7 | 1 | Reserved flags0 |
| 8 | 16 | Storage incarnation |
| 24 | 16 | Owner ID |
| 40 | 8 | Owner generation, nonzero |
| 48 | 8 | Release sequence, nonzero |
| 56 | 94 | Exact committed terminal ACK3, including its CRC |
| 150 | 32 | Full authentication tag |

The tag is `HMAC-SHA256(key, domain || wire[0:150])`, where the domain is the ASCII string `AURA-A04-OWNER-RELEASE-v1` followed by **exactly one NUL byte**. Device and capture IDs are inside the authenticated ACK3. No unkeyed SHA or CRC is considered authentication. The implementation follows [RFC2104](https://www.rfc-editor.org/rfc/rfc2104); known-answer checks use [RFC4231](https://www.rfc-editor.org/rfc/rfc4231).

The trusted context contains device ID, storage incarnation, owner ID, owner generation and a32-byte secret. It must come from trusted enrollment/state, never from the request. Require an independent cryptographically random key for every device/owner generation. The nonzero-key check catches zero initialization only; it cannot establish entropy. Keys must not be derived from public IDs, timestamps, archive hashes, Bluetooth addresses or portal bearer tokens. No enrollment path or random-number generator is supplied here. All test keys and IDs are public synthetic values.

## API and mandatory controller boundary

`aura_release_authenticate()` verifies canonicality, the complete32-byte MAC without early exit, context, terminal ACK3 syntax/CRC/device ID and byte-for-byte equality with the trusted expected94-byte ACK3. Output remains unchanged on failure. It accepts terminal statuses1 and2 syntactically. Scalar bounds match the ACK3 wire reader: sequence at most1,000,000, encoded bytes at most2^40 and sample count at most2^63-1. It does not prove that these counts describe a valid archive or increase the C writer's256MiB quota; the independent journal scan must do that.

The expected receipt must be obtained from a full independent scan of an immutable inactive capture, with no metadata fault, unresolved continuation or ambiguous allocation. **An open receipt or an export-synthesized interrupted seal cannot authorize release.** A status2 receipt is usable only if its exact terminal seal is durably present and all retained extents are accounted for.

`aura_release_validate_next(sequence, persisted_floor)` only validates that sequence equals floor+1. It rejects replay, gaps, zero and an exhausted floor; it never advances state. Authentication is separate so a controller can authenticate an identical already-committed retry, then compare the exact envelope against its durable grant. Authentication success alone is never sufficient to erase.

The future controller must serialize verification and grant commitment, persist/read back the authenticated envelope, original allocation extents and new replay floor before any erase, then fence those extents against reuse until durable completion. The floor remains monotonic across owner changes within a storage incarnation. Rekey must preserve that floor and atomically advance generation with a fresh key; it cannot proceed during an unresolved grant. Lost or corrupt authority state must fail closed. Capture-ID reservation and nonreuse must survive reclamation separately. These storage obligations are not implemented or tested by this module.

`aura_release_sign()` is a byte-serialization/authentication helper for tests and companion interoperability. It accepts syntactically valid terminal receipts; it is not a trusted durable-receipt issuer and does not infer permission. A companion issuer must independently revalidate committed receiver data, obtain explicit release permission and durably record the exact outgoing envelope before transmission. Authentication asserts possession of the enrolled key; it cannot prove a remote filesystem honored a flush or protect against a malicious authorized key holder.

The bounded HMAC helper accepts key/message lengths 0..256 bytes, including the RFC long-key cases. RLS1 uses a 32-byte key and a 176-byte domain/body input (25 ASCII bytes, one NUL, 150 body bytes). The module uses no heap and retains no state. Its local pads and intermediate tags are cleared, but this is not a whole-system secret-erasure guarantee: the existing SHA routine, compiler and caller also use stack/storage. Source-level fixed-iteration tag comparison is tested functionally, not measured for timing or physical side channels.

## Integration and verification

Compile `src/aura_release_auth.c` together with existing `src/aura_archive.c`, include `include/` and the pinned Opus public headers required by the archive header. No Opus library or mock cryptography is needed for this standalone authentication harness. The integrated `scripts/build.ps1 -Mode all` runs it and writes [the source-bound report](verification/release-auth.json), then cross-compiles the actual functions into the DK probe. The probe only retains their addresses and a zero-initialized context for ABI/resource inspection; it provisions no owner and performs no physical authentication or erase. The published A03 release is unchanged.

From the workspace root:

```powershell
python firmware/a04/scripts/verify_release_auth.py
```

The script uses the existing local Zig compiler when present, or accepts `--cc PATH`. It compiles the actual production sources with C11, `-Wall -Wextra -Werror -UNDEBUG -O2`, runs13 C test groups and independent Python standard-library HMAC/struct/CRC comparisons in both directions. It emits JSON with exact and LF-normalized source hashes, binary hash and transcript to stdout. Compilation occurs in a temporary directory; the script does not overwrite source or verification artifacts. The tests cover RFC4231 cases1..7 (case5's published128-bit prefix only), every bit of the entire182-byte message, authenticated malformed fields, context/key/receipt substitutions, lengths, initialization, replay, overflow and the mandatory domain NUL. RLS1 always requires the full256-bit tag.

No final A04 hardware target, BLE owner enrollment, secure boot, protected key store, secure capture-ID reservation or rollback-resistant physical storage is established here. A03 encrypted Just Works pairing supplies none of those application-level guarantees. Device challenge/response and companion permission/outbox integration remain separate work. The primitive is suitable for portable testing; it is not a product security qualification.
