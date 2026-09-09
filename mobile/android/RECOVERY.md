# Foreground recording recovery

`CaptureRecovery` joins the validated transfer protocol, durable Android source
store and playable library. `AndroidGattConnection` supplies the Android GATT
transport beneath it. These classes do not yet exchange
[ASC1 owner proof](../../docs/a04/session-auth-v1.md) with the implemented
[radio DK service](../../firmware/a04/radio/README.md), supply trusted owner-context
custody/enrollment, or activate recovery from the consumer Activity. That Activity still offers local
file import. A public device ID, advertised name, Bluetooth address, bond or
successful HELLO must never become an ownership credential.

## Lifecycle and visible truth

One worker owns a recovery pass. `start()` enters the foreground and requests a
pass; `retry()` keeps at most one follow-up wake. `setForeground(false)` closes
the connection, interrupts processing and invalidates old callbacks. `cancel()`
stops the current pass, while a subsequent `start()` or `retry()` can resume.
`close()` permanently ends this owner. No periodic background service is implied.

The immutable observer distinguishes:

- `CONNECTING` and `CATALOG`: establishing the transport and discovering sources.
- `DOWNLOADING`: received bytes may include a RAM-only partial record; committed
  bytes identify verified complete records already stored in SQLite.
- `SOURCE_PRESERVED`: every selected byte and the matching FINISH are committed.
- `PROCESSING`: the preserved original is being independently decoded/imported.
- `READY`: the real platform decoder and library publication have succeeded.
- `SOURCE_SKIPPED` or `ATTENTION`: fixed reasons describe unresolved sources;
  exceptions containing identifiers, paths or source text are not displayed.

Counters count distinct source outcomes for the pass. A later successful retry
resolves that source's earlier failure. Empty captures can be preserved without
becoming playable. Observers must return promptly and retain the generation when
posting asynchronous UI updates; a stale observer task cannot represent current
recovery. This is an integration contract, not a completed Bluetooth screen.

## Exact recovery across connections

The current transfer coordinator starts with HELLO against separately trusted
device/incarnation identities. The radio DK target additionally requires L4 and
ASC1 before HELLO; implementing that prerequisite in the Android connection is
still work. LIST supplies a bounded catalog; invalid or faulted sources are not
marked saved. SELECT verifies the requested manifest, physical receipt and
allocation identity. The selected source is pinned for the whole pass, including
reconnects: changed receipts/lengths remain a source conflict rather than silently
replacing an in-progress recording.

`DownloadStore` replays exact committed rows before publishing a resume offset.
READ continues from that boundary, then uses received offsets within the same
live parser. A reconnect discards only the incomplete RAM record. Reaching the
file length still requires an explicit zero-byte READ at EOF before FINISH; this
exercises the C cursor's seek/EOF gate even for a previously completed local
source. FINISH must match SELECT exactly. Physical OPEN provenance remains OPEN
when the export contains a derived interrupted seal.

Transactions are nonzero u16 values. The owner renews the connection before
exhaustion, reselects the same pinned source and resumes its committed boundary.
Repeated rollover without record progress has a finite failure bound. Connection
retries and catalog refreshes also have finite budgets. No retry, FINISH or
notification completion authorizes erasure or media repair.

The configurable development budgets distinguish ordinary commands from full
source verification/seek. Defaults allow 30 seconds for ordinary operations and
60 minutes for full source scans; these are uncalibrated upper bounds, not
measured throughput or acceptable consumer latency. Physical NAND/radio timing
must determine production deadlines. Foreground cancellation remains available
during a long operation.

The radio DK's ASC1 grant has its own ten-minute absolute lifetime. The phone's
longer command budget does not renew that grant. Matching proof renewal and
large-source recovery still need Android integration and measured device timing.

## Android GATT ownership

Construction starts no radio or thread. The first background `exchange()` lazily
connects, discovers exactly one matching service/characteristic set, negotiates
MTU and writes the notification descriptor. Transfer readiness requires the
successful descriptor callback, not merely a connected state. Commands use
write-with-response; ATT write success is distinct from a logical reply.

One handler thread serializes platform operations. Callbacks validate the GATT
instance and connection generation before copying bounded notification values.
API33+ uses the value-based callbacks/writes; older platforms copy the mutable
value immediately. The actual negotiated MTU bounds every fragment. Current and
one prior-completed parser permit exact late duplicates without satisfying a new
transaction. A service-change callback terminates the cached GATT lineage.

There is at most one exact command retry after successful ATT write completion
when a logical reply is missing. Unknown ATT completion is not retried. Gaps,
conflicting bytes, failed subscription, unexpected MTU changes and expired
deadlines close the connection. Cross-thread close wakes the blocked worker and
invalidates callbacks before deferred platform cleanup.

## Evidence and remaining integration

The [Android verification record](VERIFICATION.md) identifies actual executions
and their limits. Scripted-connection tests use real SQLite and platform decoding
with the fixed C fixtures. The separate [Netsim/Bumble fixture](ble-fixture/README.md)
exercises real Android GATT callbacks against a Python virtual peripheral; it is
not the Zephyr transfer engine, authenticated enrollment or physical radio.

The [Zephyr radio DK adapter](../../firmware/a04/radio/README.md) now implements
the matching archive service plus a separate ASC1 characteristic. Its bounded
owner/mailbox, immutable notification slot and independent authorization expiry
are described in [radio integration](../../docs/a04/radio-integration.md).
Its source/host checks do not establish executed Zephyr SMP or physical pairing.

Consumer access still requires the Android ASC1 proof exchange, trusted
owner-context custody and reviewed enrollment, application lifecycle/UI wiring,
and an actual microphone/NAND-to-phone recovery trial. Android's
foreground/background restrictions and hardware tests remain independent of a
successful emulator run. Original source storage and playback publication are
documented in [DOWNLOADS.md](DOWNLOADS.md).
