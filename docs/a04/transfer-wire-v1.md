# A04 transfer wire version 1

This locks the byte contract for the portable firmware command owner and Android
codec. It is not evidence of a working GATT connection, ownership enrollment or
phone download. The service UUIDs and response fragment header are defined in
[mobile-transport.md](mobile-transport.md). No command starts a microphone,
changes ownership, provisions secrets, formats media or authorizes release.

All integers are unsigned little-endian. Commands contain exactly the listed
bytes, with no padding/trailing data. Every command is at most 20 bytes and starts
with `version:u8=1, opcode:u8, transaction:u16`. Transactions are nonzero and
strictly increase within a connection; gaps are allowed. Reconnect before u16
exhaustion, retaining only independently verified complete-record resume state.

## Commands

Offsets include the 4-byte command header.

| Opcode | Name | Bytes | Fields |
| ---: | --- | ---: | --- |
| 1 | HELLO | 4 | None |
| 2 | LIST | 10 | revision:u32 at4; catalog index:u16 at8 |
| 3 | SELECT | 20 | capture ID[16] at4; nonzero |
| 4 | READ | 18 | handle:u32 at4; export offset:u64 at8; requested:u16 at16 (1–256) |
| 5 | FINISH | 16 | handle:u32 at4; expected export bytes:u64 at8 |
| 6 | CANCEL | 8 | handle:u32 at4 |

Revisions and handles are nonzero. Archive offsets/lengths are at most 320 MiB,
the existing complete-file reader bound. Zero-valued expected export length is
syntactically permitted but cannot match a canonical selected archive. Neither
an encoded-payload count nor an unverified file length is a resume position.

## Logical responses

Every response starts with `status:u8, opcode:u8, transaction:u16` (no version
byte). Opcode/transaction must match the outstanding request. Status is 0 OK,
1 BUSY, 2 INVALID, 3 NOT_FOUND, 4 IO_ERROR, 5 FORBIDDEN, 6 END_OF_LIST, 7 STALE or
8 CONFLICT. An error is exactly four bytes, with no success fields. Success
layouts below include the common header in their total length and offsets.

| Command | Total bytes | Success fields |
| --- | ---: | --- |
| HELLO | 46 | device ID[16] at4; storage incarnation[16] at20; revision:u32 at36; catalog count:u16 at40; max logical bytes:u16 at42 (=512); max chunk:u16 at44 (=256) |
| LIST | 80 | revision:u32 at4; index:u16 at8; exact manifest[68] at10; verification:u8 at78; source flags:u8 at79 |
| SELECT | 195 | handle:u32 at4; exact manifest[68] at8; physical ACK3[94] at76; physical bytes:u64 at170; export bytes:u64 at178; derived seal:u8 at186; allocation generation:u64 at187 |
| READ | 22 + count | handle:u32 at4; absolute export offset:u64 at8; count:u16 at16; data[count] at18; IEEE CRC32:u32 immediately after data |
| FINISH | 119 | handle:u32 at4; physical ACK3[94] at8; export bytes:u64 at102; derived seal:u8 at110; allocation generation:u64 at111 |
| CANCEL | 8 | cancelled handle:u32 at4 |

HELLO catalog count is 0–128, the current bounded journal inventory. Manifest
and ACK3 are the exact canonical AUR3/ACK3 formats; CRC32 covers only
READ data. IDs/incarnation and allocation generation must be nonzero. The
derived-seal byte is exactly 0 or1. READ count is 0–requested and at most256;
a zero-data response is valid only at the selected export EOF after cursor
completion. Short nonempty reads are normal. No successful READ is a durable
phone acknowledgement.

LIST verification values are 0 unverified, 1 verified OPEN, 2 verified FINALIZED,
3 verified INTERRUPTED and 4 invalid. Source flags are bit0 metadata fault,
bit1 globally unassociated source, bit2 journal fault and bit3 different device
ID; all other bits are zero. LIST is a privileged catalog snapshot, not proof of
allocation ownership or export eligibility. The count/index refer to the mounted
catalog, including unavailable entries; allocation is independently checked at
SELECT. A stale revision returns STALE; an index at or beyond count returns
END_OF_LIST. No listing issues a physical receipt.

SELECT supports only independently verified owned v2 allocations whose device
and incarnation match the authenticated session's trusted context. Its capture
ID must equal the existing generation-derived capture ID. Matching-device legacy
allocations, foreign incarnations and invalid generation-derived identities
return FORBIDDEN; they are not relabelled under the current owner. A missing full
device/capture identity, including a capture belonging only to another device,
returns NOT_FOUND.
The manifest, physical receipt, lengths and generation remain bound to the
handle. A physical OPEN receipt requires derived=1 and export=physical+120;
a terminal physical receipt requires derived=0 and equal lengths.

## Admission, retries and lifecycle

One serialized storage owner owns commands, journal access and source snapshots.
The trusted caller supplies an already-authenticated connection context; no
command field, public identity, bond, hash or plaintext A04B context grants
access. An unauthorized session cannot read responses or catalog data. Actual
enrollment and GATT security must be implemented before product access is enabled.

Only one command or response transmission may be outstanding. An exact retry
of the last pending command joins it. An exact retry of the last completed
command resends its immutable cached response. A retry while that response is
already being transmitted joins its current delivery instead of starting a
parallel notification chain. Changed bytes with the same
transaction in a bounded 4–20 byte envelope return an admission conflict, even
when the changed version/opcode/body is otherwise malformed. Outside that
envelope length, admission returns invalid. Other commands must pass canonical
validation before transaction age and busy checks. Older valid transactions are
stale. A new
transaction while work or response delivery is pending returns admission busy
without replacing state or consuming that transaction. Malformed commands also
fail admission without consuming a transaction. These admission errors are not
competing logical responses under an already-pending transaction.

The transport marks response delivery complete only after its notification chain
finishes, using the engine's connection, transaction and fresh internal delivery
token. A retry after completion obtains a new delivery token; late completions or
fragment requests for an older delivery cannot clear or use the newer gate.
One egress owner coalesces work for each token. That releases command admission
and retains the last response for exact retry. It does not claim that the phone
saved audio. Each response/fragment copy
rechecks authorization, connection generation and source epoch. A changed epoch
invalidates the handle, pending work and cached response; it never rewrites a
partly delivered response. The transport must cancel old notifications, report
the admission/connection failure and reconcile with a new transaction. Catalog
revisions are checked, connection-scoped counters; they never truncate or reuse
a u64 journal epoch. Handle and generation counters fail closed on exhaustion.

SELECT creates a fresh handle after bounded source verification. The first READ
seeks once to a complete-record boundary. Later READ offsets must equal the end
of the previous DATA, even when that position falls inside a record. FINISH is
accepted only once the requested stream reaches the advertised export length;
it drives the cursor's remaining replay and third physical verification before
issuing success. Unexpected extra DATA fails. First READ at export EOF is allowed
but still verifies the full source; the caller must already possess the exact
complete archive and independently validate it before considering it saved.

Ordinary CANCEL cannot displace a pending command; it obeys admission ordering.
Disconnect, loss of ownership and authorization expiry must end the session,
revoking access as well as its volatile work. A local capture request or transfer
timeout uses the separate immediate work-cancellation hook between bounded owner
steps; that hook preserves the authenticated session. Cancellation
does not change source bytes or authorize erasure. The future GATT owner must
drop stale callbacks and invalidate queued notification copies as well as the
command engine. No concurrent raw-media mutation is supported.
