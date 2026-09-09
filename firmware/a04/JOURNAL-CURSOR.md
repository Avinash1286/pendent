# Bounded A04 journal export

The [cursor API](include/aura_journal_cursor.h) supplies the storage foundation
for resumable phone transfer. It is a read-only, statically allocated C state
machine over the existing AUR3 journal. It does not implement BLE, phone
enrollment, a durable Android download transaction or source deletion.

## Selection, streaming and completion

`open(cursor, journal, device_and_capture_id)` copies the exact 32-byte identity
from the caller and selects its catalog entry without reading NAND. A catalog
index is never a persistent identity. Active captures, pending capture bindings,
journal faults and unassociated quarantined material deny selection.

Call `verify_step()` until READY. Each call reads at most one NAND page and
replays at most that page's 1980-byte record area. It checks the entire selected
chain, including every remaining data slot, continuation header and checkpoint.
READY binds the exact manifest, independently verified physical ACK3, physical
byte length, v1/v2 allocation identity and expected export length. This is source
verification; nothing has been saved to a phone.

After READY, call `seek()` once with zero or a retained complete-record boundary.
Then call `read()` with a caller-owned buffer of 1–256 bytes. The cursor makes one
linear replay from the beginning, validates the requested boundary against real
records, skips its verified prefix and copies the remaining bytes. A seek into a
manifest, AFR3 or ASE3 fails instead of rounding. Seeking to physical EOF or
export EOF is supported and still performs verification. Records and NAND pages
may span several chunks. The cursor keeps its own bounded page payload; no
returned bytes alias NAND scratch, DMA memory or its internal buffer.

`read()` returns DATA with an absolute offset and length, PENDING with zero
bytes, a negative failure, or zero for FINISHED. **The final DATA response is not
FINISHED.** After replay it checks the selected physical receipt and allocation,
then performs a third complete bounded source scan before returning FINISHED.
This detects source changes behind the replay cursor as well as changes to later
pages. All output remains temporary until FINISHED. The transport must cache its
own immutable command response for retries; calling sequential `read()` again
advances the cursor and is not a command retry.

For a physical OPEN prefix, an interrupted ASE3 is synthesized only in the
export buffer. Its extra 120 bytes do not become NAND data or a physical receipt.
`get_info()` returns the same physical ACK and allocation after completion as at
selection. A derived interrupted export keeps unknown original duration and
never grants release authority.

## Failure and ownership

All calls run under one serialized storage owner. A local capture request must
cancel/preempt the cursor before beginning other work. Journal mount, writes,
preparation, ownership binding and storage ownership/error transitions invalidate
its volatile epoch. The process-wide counter prevents same-address remount from
reusing an epoch; exhaustion fails closed. Idle clock servicing and verification
do not invalidate it. Check the epoch before every step, including draining
buffered bytes and returning cached completion.

Any external media operation must call `aura_journal_invalidate_exports()` before
changing storage. This is not a lock: raw concurrent access, DMA races, malicious
media substitution and unsignalled ownership replacement are outside the API
contract. Three scans do not create an atomic flash snapshot. The future BLE
owner must serialize its operations and invalidate connection handles/cache on
disconnect, cancellation and media transition.

Cancellation and stale handles clear only volatile state. They do not invalidate
a healthy capture or alter its bytes. An actual failed selected-source validation
invalidates its old cached journal receipt, so callers cannot reuse that receipt
as fresh evidence. Invalid seek positions and argument errors confer no rights.

The shared walker preserves the legacy journal's torn-tail rule: one ECC-readable
blank or CRC-invalid tail slot may end an OPEN prefix only if all later slots and
metadata remain consistent. A later valid/nonblank page, contradictory checkpoint
or valid-CRC malformed record fails. The new cursor is deliberately stricter than
legacy salvage: **any unreadable selected-chain slot and any globally unassociated
quarantined block deny successful transfer**. Corrected ECC is accepted and
counted. This does not scan all unowned chip payloads or prove total media health.

## Integration and evidence

The wired DK bench uses this cursor for EXPORT while retaining its existing
request/response format. It remains a synchronous UART command: cooperative
kernel yields do not add wire-level resume, command preemption or BLE scheduling.
The [mobile transport proposal](../../docs/a04/mobile-transport.md) still needs
its command codec, GATT service, authenticated enrollment and Android recovery
coordinator. The separate Kotlin response-fragment parser is not a connected
radio path.

Run the focused cursor host suite with:

```powershell
.tools/zephyr/venv/Scripts/python.exe firmware/a04/scripts/verify_cursor.py
```

Its [report](verification/journal-cursor.json) and
[transcript](verification/journal-cursor-host.txt) bind tested sources and
execution. Eighteen host groups pass, with at most one NAND read per call. The
finalized real Opus fixture exports exactly 37,040 bytes; the OPEN fixture retains
its exact 36,514-byte physical prefix and exports 36,634 bytes with its derived
seal. The cursor uses 3,808 bytes on the host ABI and 3,800 in the actual ARM ELF.
The existing journal/recorder/audio/storage regressions also pass; rerun them
when changing the shared page walker. The separate bench's
[ELF report](bench/verification/arm-resources.json) checks actually linked cursor
functions and allocated objects. Host read counts are operation bounds, not
measured NAND, radio, STOP latency, runtime stack or wearable qualification.
