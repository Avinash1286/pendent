# A04 isolated control ledger

Status: **implemented and tested against the strict host NAND model, with a separate W25N control-pair adapter; no physical test**. This primitive stores opaque bytes. The separate [storage owner](STORAGE.md) supplies durable identity and owner-release semantics; this ledger alone does not authenticate a receipt or erase audio.

The API is [aura_control.h](include/aura_control.h). It accepts exactly two explicitly configured distinct physical block numbers and a nonzero 16-byte storage domain. The caller owns one serialized context and at most 49152 bytes of snapshot input/output. No heap, threads, GPIO assignments, automatic block discovery, or automatic format exists. The block-count bound 1–1024 and both indices are checked before access. Both blocks must remain reserved outside this module; passing them to the audio allocator would violate the ownership contract.

## Preservation and availability

Provisioning is an explicit operation. Before any erase, **all 64 main pages of both blocks** must be fully readable, ECC-clean and FF, and both factory/LUT exclusion checks must pass. Existing or damaged authority cannot be repaired by calling provision. Cold open only reads the configured pair.

Each replacement writes a complete snapshot into the inactive block, after a fresh successful erase and a complete ECC-clean FF check. Pages are programmed once, in increasing order; pages 0 and 1 are never programmed. The module reads back all 2048 bytes of every programmed page. An uncertain program completion can succeed only through exact usable-ECC readback, without repeating Program Execute. A reported program failure never becomes same-call success. A lost or failed erase is never promoted from FF bytes and no program follows it in that call.

The last program is a commit page binding the complete snapshot. A final full-block scan must agree with the exact intended commit digest, byte count, generation and parent before store returns success. Only then does the selected current slot change. The previously selected snapshot is preserved throughout this attempt. Before a subsequent erase, both slots are reread and must still establish the same current generation and digest; stale contexts cannot destroy an updated state.

After a power cut, a completely valid newer snapshot with the right parent is selected even if the interrupted caller never received success. A before-program cut that leaves the entire inactive block FF can leave the previous state available. A partial erase of an older snapshot can also be resolved when its independently valid retained commit hash exactly matches the fully valid current snapshot's parent. The older header must be blank or still exactly bound by that commit; unreadable pages, a torn nonblank header, or a recognized contradictory generation prevent this exception. This proof relies on correct erase-before-program sequencing and non-adversarial media. No old snapshot is used as authority in this case.

**A torn, unreadable, unknown, or ambiguous newer candidate fails closed.** The prior snapshot may still be physically intact, but it is not returned as current authority or an old replay floor. A failed context refuses load/store until a successful open establishes authority. This protects against rollback through an ambiguous commit, at the cost of availability after some normal power cuts. There is no automatic repair method. Operators must not simply reformat to recover: that could reset identity reservations or a replay floor after irreversible work. A separately designed trusted recovery protocol is outstanding.

Successful load rereads both slots and then validates the selected snapshot while copying it. A stale context is rejected before output. Output bytes are usable only on success, and the output count is zero on failure except where the count pointer itself is invalid or aliases protected storage. The count and output must not overlap each other or the control context. Header-declared lengths and every copy are bounded by the caller's actual output capacity.

## Wire format

All integers are little-endian. Each programmed main page is exactly 2048 bytes. CRC32 at offset 2044 covers bytes 0–2043, using the existing archive IEEE CRC implementation. SHA256 hashes the entire 2048-byte page, including its CRC. Distinct `A4CH`, `A4CB`, and `A4CC` magic/type fields and the explicit storage domain separate the hash uses. These are public integrity hashes, **not keyed authentication**.

| Page | Contents |
|---|---|
| 0–1 | Reserved main pages remain FF; factory marker/spare checks belong to the NAND backend |
| 2 | `A4CH` snapshot header |
| 3 onward | Zero through 26 `A4CB` body pages, carrying at most 1920 bytes each |
| After the last body through 62 | Entire main pages must remain FF |
| 63 | `A4CC` commit, programmed last |

Common fields are magic at 0, version 1 at 4, type 1/2/3 at 5, layout-size field at 6, physical block uint16 at 8, configured slot 0/1 at 10, zero at 11, generation uint64 at 16, and storage domain at 32. The layout-size field is **124 for body pages**, whose payload starts at 124, and 128 for header/commit layouts. It is a canonical layout discriminator; header/commit reserved regions and commit digests extend as specified below.

Header: snapshot length uint32 at 12; parent generation uint64 at 24; parent commit SHA256 at 48; body count uint16 at 80; zeros at 82–2043. Generation starts at 1, is nonzero, and increments by exactly one. Parent is generation minus one. Generation 1 has an all-zero parent hash; later generations require a nonzero parent hash. Generation `UINT64_MAX` is readable but cannot be replaced.

Body: zero-based body index uint16 at 12; payload length uint16 at 14; payload offset uint32 at 24; total snapshot length uint32 at 28; preceding page SHA256 at 48; zeros at 80–123. Payload starts at 124, with unused bytes FF through 2043. The first body links the complete header hash; each later body links the complete preceding body hash. Bodies cannot be reordered, skipped, lengthened, or moved between slots/domains without detection by a complete scan.

Commit: length, parent, parent hash and body count repeat the header's fields; zeros at 82–87; complete header SHA256 at 88; final body SHA256 at 120 (header hash for an empty snapshot); zeros at 152–2043. The commit's own complete-page SHA256 identifies the snapshot. When both slots are valid, the newer generation must be exactly one greater and link the older commit hash. Equal generations, gaps, or different parent hashes cannot elect authority.

## Destructive interface constraint

`aura_control_io.erase_control` is a **separate control-block capability**. The module's private erase wrapper rejects every block outside the configured pair and the selected current slot. The integration must independently enforce the configured pair, preserve factory-marker/LUT exclusions, serialize the entire operation, check completion/status/readback and establish fresh-erase program permission. The host adapter does this targeting check independently of the module.

The [W25N adapter](W25N-ADAPTER.md) now supplies this callback through an explicitly configured, immutable control pair. Its ordinary `aura_nand_io.erase` continues to refuse populated blocks and excludes the control pair. The dedicated view independently rejects every non-control target. This supports control rotation in command-model tests; it supplies no populated-audio erase capability. Open/load work with a read-only backend, but provision/store require the separate callback.

## Security and remaining integration

The [AST1 storage snapshot](STORAGE.md) now binds identity reservations, storage/owner generations, release replay floor, exact authenticated release envelope and fenced block extents. Those semantics belong to the separate storage owner. A receipt alone is not deletion authority: the owner independently verifies the authenticated command, exact committed source, finalized-only policy and scope before committing a grant. Its privileged audio-erase callback is still implemented only by the host test model.

CRC/SHA256 detects accidental damage and binds the pair under the stated correct-operation model. An attacker who can rewrite raw NAND can recompute public hashes. Restoring an older exact copy of both blocks is also undetectable without a separately trusted external anchor. The tests deliberately demonstrate this rollback limit. Neither a future MAC nor the existing release-command MAC alone provides physical anti-rollback. There is no key storage, ledger MAC, ownership transfer, persistent floor semantics or trusted recovery implementation here.

Two fixed control blocks also lack wear migration and bad-control-block replacement. A bad or unreadable member fails closed; this port never sacrifices the surviving member to recover service. No claim about endurance, erase timing, real-time deadlines, physical power failure or battery behavior follows from these host tests.

## Verification

Run the isolated test:

```powershell
& .tools/zephyr/venv/Scripts/python.exe firmware/a04/scripts/verify_control.py --build
```

It compiles the actual control/archive code and existing strict NAND model with the pinned Zig C compiler (`-std=c11 -Wall -Wextra -Werror -O1`). Test assertions remain active even when the compiler defines `NDEBUG`. The Python verifier independently decodes the emitted two-block image, recomputes all CRCs and SHA256 links, checks exact 49152-byte and 1921-byte payloads, and rejects a noncanonical body header size even with a repaired CRC. Output defaults to ignored `.tools/a04-control/evidence/`, including the host transcript, media fixture and source-hashed JSON report.

The current suite passes **12 groups and 712 fault/rotation cases**, covering every header/body/commit in a three-body snapshot with before/partial/after program cuts, every prefix page boundary of initial/inactive/older-block erases, lost completion, program/erase failures, exact-byte PFAIL rejection, full blank-before-provision checks, all six marker locations, LUT exclusion, corrected/uncorrectable ECC, hidden material, canonical fields and parent/domain conflicts, aliased/stale output, final valid-snapshot substitution, conservative older-erase recovery, and 260 replacements with cold reopen. Every destructive callback is constrained to the pair, while an unrelated populated source-page hash and its programming history remain unchanged.

The host context is **4272 bytes**, including two 2048-byte scratch pages. A healthy cold open performs **128 main-page reads = 262144 bytes**, with no programs or erases, plus two backend bad queries. A load adds another complete pair check and selected-block scan. At maximum length a snapshot uses 26 body pages plus header and commit: 28 page programs. These counts exclude any backend's own command/status/cache/marker work. Physical operation timing remains unmeasured.

The shared `scripts/build.ps1 -Mode all` builds/runs this harness with `--build`, preserving [the source-bound report](verification/control-ledger.json), [host transcript](verification/control-host.txt) and synthetic control-pair fixture. It also cross-compiles the actual functions into the DK probe. [The ELF report](verification/arm-resources.json) measures the retained control context, storage owner, functions and a 45408-byte maximum AST1 caller snapshot. These objects remain unprovisioned: no physical pair or privileged audio-erase callback is configured. The linked reservations do not establish the complete product memory budget or runtime stack headroom.
