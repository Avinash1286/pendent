# A04 Zephyr radio integration plan

Reviewed 2026-09-09 against the local Zephyr 4.2.0 sources and the
[pinned Omi snapshot](../research/omi-source-snapshot.json). This is a proposed
adapter, not an implemented firmware GATT service, enrollment scheme or tested
radio link. The portable [transfer owner](../../firmware/a04/include/aura_transfer.h),
[wire contract](transfer-wire-v1.md) and bounded cursor already exist. Their
host/ARM checks do not demonstrate radio operation.

## Smallest application boundary

Add a separate `firmware/a04/radio/` DK application and a small proposed
`aura_gatt_zephyr.c` adapter. Keep the wired
[bench build](../../firmware/a04/bench/CMakeLists.txt) and its Bluetooth prohibition.
Reuse the bench's [storage/audio owner loop](../../firmware/a04/bench/src/main.c),
NAND configuration and local capture controls. Replace the synchronous EXPORT
dispatch in the radio application with incremental transfer steps: `k_yield()`
inside a whole export does not dispatch the owner's queued capture request.

Declare the distinct service, command WRITE-with-response characteristic and
response NOTIFY/CCC from [mobile-transport.md](mobile-transport.md). Use one
connection and one outstanding logical command. A03's
[protocol.c](../../firmware/src/protocol.c) supplies physical pairing-window and
advertising examples; its mutex waits in GATT callbacks, mutable polling reply,
integer capture IDs, DELETE and FORMAT are not the A04 interface.

## Owner mailbox and admission

The storage thread owns **every** `aura_transfer_*` call, including the functions
that perform no NAND I/O. Bluetooth callbacks never access journal scratch,
perform a scan, execute capture work or wait indefinitely for that owner.

| Entry point | Proposed responsibility |
| --- | --- |
| GATT command write callback | Check connection authorization, offset/flags and the 4–20 byte envelope; copy the command and transport generation into a bounded mailbox using `K_NO_WAIT`. Reject unavailable admission capacity immediately. |
| Connection, security and CCC callbacks | Close the admission gate immediately when required, publish a bounded lifecycle event, and schedule connection/advertising work. No storage API calls. |
| Storage owner tick | Drain revocation/capture events first, service pending audio, process one command/completion, call at most one `aura_transfer_step`, and publish a copied TX fragment. |
| Radio TX work | Check the current connection/subscription/generation gate, send one copied fragment, handle temporary resource failure with bounded retry, and never block the audio owner. |
| Notification completion callback | Queue immutable completion metadata; the storage owner validates it before advancing delivery. |

**ATT write success means mailbox receipt only.** It does not mean engine
admission, operation success or saved audio. The owner remains authoritative for
canonical commands, exact retries, busy/age conflicts and source transitions.
If owner admission later fails, terminate that connection/session and let the
phone reconcile from its committed prefix. Do not manufacture a competing
logical response under an outstanding transaction. This conservative disconnect
policy preserves the existing wire bytes; a richer asynchronous admission-status
channel would need a separately reviewed contract. Reject prepare/execute and
write-without-response forms for this characteristic.

Zephyr calls attribute read/write callbacks from its RX thread; long blocking
work there is discouraged. See the pinned
[Zephyr GATT documentation source](https://github.com/zephyrproject-rtos/zephyr/blob/v4.2.0/doc/connectivity/bluetooth/api/gatt.rst).

## One immutable notification in flight

The owner uses `copy_response`/`copy_fragment` and retains
`{connection generation, transaction, delivery token, fragment offset}` in an
owned callback slot. Coalesce identical pending retries. Only the final fragment
completion permits `response_sent`; a completed response retry gets a fresh
token. Stale callbacks must never clear a newer delivery gate.

Hold the appropriate `bt_conn_ref` until asynchronous use ends; do not reuse a
callback slot merely because disconnect/cancel was requested. Send to that exact
connection, never all subscribers. Recheck `bt_gatt_is_subscribed` and size each
fragment for the actual MTU: value at most `MTU - 3`, leaving `MTU - 11` bytes
after the eight-byte transfer header. MTU 23 remains supported.

Pinned Zephyr copies the notification payload into its ATT buffer when sending;
callback/user-data references remain relevant after that call. Its completion
callback runs on the System Workqueue. `bt_gatt_notify_cb` called from that
workqueue returns an error instead of waiting for callback resources, so use
bounded rescheduling rather than blocking the storage thread. See
[Zephyr 4.2 GATT APIs](https://docs.zephyrproject.org/4.2.0/doxygen/html/group__bt__gatt__server.html)
and [the actual payload copy](https://github.com/zephyrproject-rtos/zephyr/blob/v4.2.0/subsys/bluetooth/host/gatt.c#L2560).

## Capture, revocation and authentication

Local capture preempts between bounded owner steps: call `cancel_work`, invalidate
unsent TX copies, then prepare capture storage. This retains the authenticated
session. Ownership loss, authorization expiry or disconnect instead calls
`session_end`. CCC loss stops delivery and requires recovery. Lifecycle events
must not be lost behind a full command queue. Already submitted radio bytes
cannot be recalled; cancellation does not retract them. Notification completion
and FINISH never authorize source deletion.

Require an encrypted LE Secure Connections link and a physically bounded pairing
window, plus a reviewed ownership enrollment/session-proof provider. Bonds,
public IDs, hashes and the plaintext wired A04B context are not owner proof.
Only that trusted provider may authorize `session_begin(true)`; until implemented,
the radio service denies archive/catalog access. Never expose the bench's raw
key-bearing `PROVISION`/`OPEN` commands over BLE. No developer bypass is proposed.

Omi's pinned implementation offers useful subscription checks, connection
references and TX throttling. Its consumer pusher also dequeues before deciding
whether to send/store and ignores a failed send in the subscribed path; its
storage callback feeds automatic ring advancement. Preserve AURA's independent
durable-receipt boundary instead. Sources:
[Omi transport](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/omi/src/lib/core/transport.c#L1066),
[Omi storage](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/omi/src/lib/core/storage.c#L248).

## Resource and verification gates

The existing [wired ARM report](../../firmware/a04/bench/verification/arm-resources.json)
shows 212,104 bytes RAM used and 50,040 free. The separate
[synthetic ARM probe](../../firmware/a04/verification/arm-resources.json) measures
the transfer owner at 4,440 bytes, including its cursor. Replacing the wired
3,800-byte export cursor would add roughly 640 object bytes before other changes;
this is not a Bluetooth memory-fit result. Account separately for host/controller,
SMP/settings, ACL pools, mailbox/TX slots and stacks. Do not reduce audio/Opus
stacks without evidence.

Before enabling product access, require adapter tests for queue exhaustion,
retries, timeout, CCC changes, stale connection/delivery callbacks, close races,
capture preemption and denied authorization; a source-bound BT-enabled ARM link
and stack/resource report; and actual DK-to-Android capture/download/reconnect
tests at negotiated MTUs including 23. Until then, report portable interoperability,
cross-compilation and proposed radio behavior separately.
