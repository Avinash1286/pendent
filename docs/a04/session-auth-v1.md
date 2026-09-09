# A04 ASC1 radio session authentication, version 1

This document specifies the first bounded owner-proof provider for the A04 radio
adapter. It is an implementation contract, not evidence of executed SMP,
successful physical pairing, protected key storage or consumer enrollment.
The existing virtual Android/Bumble tests use public fixture context and do not
exercise this handshake. Source-bound provider, adapter and physical integration
results must be reported separately as they become available.

The only granted capability is the existing read-only archive transfer protocol.
There is no remote recording, key provisioning, owner replacement, release,
DELETE or FORMAT operation. In particular, ASC1 does not authorize RLS1 or erase.

## Trusted inputs and channel prerequisite

The provider receives the existing caller-owned
[`aura_release_auth_context`](../../firmware/a04/include/aura_release_auth.h):
device ID, storage incarnation, owner ID, nonzero owner generation and an
independent cryptographically random 32-byte key. These values come from the
trusted storage owner, never from the radio request. Each device/owner generation
requires a fresh independent key. Nonzero checks detect initialization errors;
they do not prove key entropy.

Initially, the context may be established by the explicitly physical, locally
trusted [A04B UART procedure](../../firmware/a04/bench/PROTOCOL.md). Its 88-byte
context contains the raw owner key. Do not expose that procedure or context over
BLE. The host's retained context and its physical UART connection are trust
assumptions; this is not consumer enrollment or protection against a hostile
local host, debug probe or firmware replacement.

Both the authentication characteristic and every transfer admission/delivery
require the current connection to be **BT_SECURITY_L4**, with a 16-byte encryption
key. L4 means authenticated LE Secure Connections. L2 Just Works, a bond, public
IDs, HELLO, CRCs and archive hashes cannot supply this authorization. The owner
proof is required on every new connection even when its authenticated bond is
reused. Zephyr defines these levels and exposes `bt_conn_get_security()` and
`bt_conn_enc_key_size()` in its pinned
[connection API](https://github.com/zephyrproject-rtos/zephyr/blob/413b789deb391d3a37d06b463288a5fe765ee57e/include/zephyr/bluetooth/conn.h).

This channel requirement matters: mutual HMAC proofs alone do not prevent an
active intermediary from relaying a live proof and subsequently reading or
injecting unprotected application traffic on a different link. ASC1 relies on
the independently authenticated L4 channel, not public addresses or its local
generation field, to prevent that substitution. It is not an application AEAD
protocol, distance-bounding scheme or physical device attestation.

## Authentication attribute and operation ordering

Use the adapter's dedicated authentication READ/WRITE-with-response attribute,
`7f520003-1b15-4f0d-8fe5-3f942170a004`, separate from the transfer command and
notification characteristics. Authentication does not consume transfer
transactions. Establish L4 and successfully subscribe to the transfer response
CCC before BEGIN; owner activation requires that subscription. Subscription
alone grants no archive access.

All writes in this version are exactly 20 bytes. Reject prepare/execute writes,
nonzero offsets, write-without-response, other lengths, unknown opcodes, and
noncanonical headers. All integers below are unsigned little-endian. There is no
struct padding, implicit string terminator or outer CRC on the wire.

| Offset | Bytes | Write field |
| --- | ---: | --- |
| 0 | 2 | ASCII `A4` (`41 34`) |
| 2 | 1 | Version 1 |
| 3 | 1 | Opcode: 1 BEGIN, 2 PROOF_FIRST, 3 PROOF_LAST |
| 4 | 16 | Client nonce or the indicated half of the client tag |

Twenty bytes fit the ATT write value at MTU 23. There is no long-write protocol.
The client serializes each write/read and waits for its platform completion.
ATT write success may mean only bounded mailbox acceptance. It is never proof
that the owner has verified the message or activated the transfer session.

The authentication READ value has one of three exact lengths:

- Four bytes `ASNO`: no challenge/grant is currently published. This is not a
  success response and carries no identity or authentication claim.
- A 144-byte ASC1 challenge, pending proof or owner activation.
- A 48-byte ASOK acknowledgement, after owner activation succeeds.

Pin a bounded copy of the current value when a read starts at offset zero.
Subsequent Read Blob offsets use that same connection/generation-bound snapshot,
even if queued work publishes ASOK meanwhile. A new offset-zero read refreshes
the snapshot. Reject out-of-range offsets and nonzero-offset reads without a
live snapshot; offset equal to the length may return zero bytes. Revocation
invalidates the snapshot immediately. Never splice ASC1 and ASOK during one
long read. Zephyr provides offset-aware
[`bt_gatt_attr_read`](https://docs.zephyrproject.org/4.2.0/doxygen/html/group__bt__gatt__server.html);
its helper does not itself establish this publication/lifetime policy.

The client polls only within its existing absolute authentication deadline,
with at most one read in flight and a bounded delay between polls. ASNO or the
unchanged ASC1 is pending, not permission. The client starts HELLO only after
validating ASOK. A malformed, changed or unauthenticated value ends the attempt.

## BEGIN and immutable ASC1 challenge

BEGIN carries a fresh 16-byte client nonce from a cryptographic random source.
The provider generates a separate fresh 16-byte server nonce. Reject all-zero
nonces as an initialization guard, and fail closed if randomness fails; never
substitute clocks, public IDs, `sys_rand_get()` or a test RNG. Zephyr's
[`sys_csrand_get`](https://docs.zephyrproject.org/4.2.0/doxygen/html/group__random__api.html)
reports failure and is intended for cryptographic random values. The final
configuration must bind it to real entropy, not `TEST_CSPRNG_GENERATOR`.

One BEGIN creates one immutable challenge for one current connection lineage:

| Offset | Bytes | ASC1 field |
| --- | ---: | --- |
| 0 | 4 | ASCII `ASC1` |
| 4 | 1 | Version 1 |
| 5 | 1 | Algorithm 1: full HMAC-SHA256 |
| 6 | 1 | Scope 1: read-only archive transfer |
| 7 | 1 | Flags 0 |
| 8 | 16 | Trusted device ID |
| 24 | 16 | Trusted storage incarnation |
| 40 | 16 | Trusted owner ID |
| 56 | 8 | Trusted nonzero owner generation |
| 64 | 8 | Nonzero local connection/session generation |
| 72 | 16 | Exact echoed client nonce |
| 88 | 16 | Fresh server nonce |
| 104 | 4 | Proof lifetime, exactly 30,000 milliseconds |
| 108 | 4 | Reserved zero |
| 112 | 32 | Full server authentication tag |

The local generation must not repeat within a process lifetime; exhaustion
fails closed. It is a stale-callback discriminator, not secret entropy or a
persistent replay counter. Fresh server randomness prevents replay across cold
starts where the local generation may restart. Neither party accepts caller-
selected server nonces or substituted trusted context.

Use the existing bounded
[`aura_release_hmac_sha256`](../../firmware/a04/src/aura_release_auth.c) primitive,
with distinct domains for each role. Each domain below is ASCII followed by
**exactly one NUL byte**. Domain strings themselves are not wire fields.

```text
serverTag = HMAC-SHA256(ownerKey,
    "AURA-A04-SESSION-SERVER-v1\0" || ASC1[0:112])

clientTag = HMAC-SHA256(ownerKey,
    "AURA-A04-SESSION-CLIENT-v1\0" || ASC1[0:144])

confirmTag = HMAC-SHA256(ownerKey,
    "AURA-A04-SESSION-CONFIRM-v1\0" || ASC1[0:144] || clientTag[0:32])
```

The domains including their NULs have lengths 27, 27 and 28 bytes. The resulting
HMAC input lengths are 139, 171 and 204 bytes, within the existing 256-byte bound.
All tags are 32 bytes; no shortened proof is accepted. This reuses standard
[HMAC](https://www.rfc-editor.org/rfc/rfc2104) and its
[SHA-256 known-answer vectors](https://www.rfc-editor.org/rfc/rfc4231), not RLS1's
release domain or release sequence.

Before sending proof, the client validates every canonical field, exact trusted
identity/incarnation/owner/generation, its own fresh nonce and the full server
tag. It retains the exact challenge bytes; parsing and rebuilding a different
equivalent transcript is not allowed. Fixed-iteration full-tag comparison and
clearing temporary secret material are required at source level. They do not
establish measured timing resistance or whole-system secret erasure.

## Split proof and explicit ASOK grant

PROOF_FIRST carries `clientTag[0:16]`; PROOF_LAST carries `clientTag[16:32]`.
FIRST must precede LAST for the current challenge. The provider compares the
complete reconstructed tag only after both halves are present and the challenge
is still live. No partial match authorizes anything. The provider may construct
its private confirmation at this point; this does not publish it to the radio.

Following a valid proof, the serialized storage owner rechecks the current
connection, L4/key length, trusted context and revocation generation, then calls
`aura_transfer_session_begin(true)`. If activation fails or an intervening event
revokes access, publish no ASOK and close the connection. The provider's local
challenge generation and the transfer engine's generation remain separate
tokens; the owner must retain their exact association.

Only after that activation does authentication READ publish:

| Offset | Bytes | ASOK field |
| --- | ---: | --- |
| 0 | 4 | ASCII `ASOK` |
| 4 | 1 | Version 1 |
| 5 | 1 | Scope 1: read-only archive transfer |
| 6 | 2 | Reserved zero |
| 8 | 8 | Exact ASC1 generation from offset 64 |
| 16 | 32 | Full `confirmTag` defined above |

The client accepts exactly 48 bytes, validates every header field and generation,
and verifies the confirmation tag against its retained challenge and client tag.
ASOK is bound to that handshake and the current L4 connection. It is not a bearer
token reusable on reconnect, a durable phone receipt or proof of source storage.

## Retry, expiry and immediate revocation

State is bounded: one connection, one challenge, one proof and one most-recent
canonical auth write. An exact retry of that most-recent accepted write is
idempotent. It returns the existing result without regenerating nonces,
restarting verification, activating a second transfer session or extending any
deadline. Earlier writes after advancing to a new step, changed bytes under a
step, reordered proof halves and malformed proofs fail the connection. A second
BEGIN cannot replace the challenge. Expiry/revocation takes precedence over a
cached retry. A failed attempt requires a fresh connection and fresh nonces.

Proof must finish strictly before `BEGIN accepted time + 30,000 ms`, using a
trusted monotonic clock. Check the deadline before accepting each proof half,
before verification and before owner activation. A stalled mailbox cannot turn
an expired proof into a valid grant. The grant expires strictly before
`complete proof acceptance time + 600,000 ms`. Time spent waiting for owner
activation consumes that same grant budget; activation never restarts it.
Overflow, backward time or missing trusted
state fails closed. Polls and ordinary transfer commands do not renew it.

The ten-minute grant is an initial bounded policy, not measured large-source
throughput. A scan/export that cannot finish inside the remaining grant must
stop and preserve source and committed phone data. The current larger phone
operation timeout does not override this authorization deadline. Reliable
completion of such sources needs a separately reviewed and measured renewal
plan; repeating an incomplete full verification is not claimed to solve it.

Disconnect, L4/security loss, owner/context replacement, explicit local revoke,
auth expiry or connection-generation replacement closes the admission gate
immediately, before enqueuing cleanup. CCC loss also ends this initial radio
lineage. Revocation must not be lost behind a full ordinary command queue.
The storage owner then ends the exact transfer session; radio work discards
unsent fragments and invalidates read/proof snapshots. Recheck the gate before
admission, each storage step, response publication and asynchronous send.
Already submitted radio bytes cannot be recalled. Old callbacks may release
their own resources but cannot reopen or complete a new session.

Local capture preemption is separate: cancel transfer work and unsent copies at
a bounded owner step, retaining the live grant only if all its other conditions
still hold. No cancellation changes NAND authority or grants erase permission.

## Physical pairing procedure for the initial UART bench

Initial pairing requires an explicit local `PAIR` action opening a 60-second
window on the physically trusted UART or equivalent physical control. It may
open only with trusted owner context loaded and capture inactive. No BLE command
opens, extends or replaces this window. A second local action while it is open
does not extend that same window. Use one selected pairing connection and at
most three admitted attempts per window; exhaustion closes it.

Register Zephyr auth callbacks before advertising/security begins. Enable
`BT_SMP`, `BT_SMP_SC_ONLY`, `BT_SMP_APP_PAIRING_ACCEPT` and a 16-byte minimum key;
request `bt_conn_set_security(conn, BT_SECURITY_L4)`. `BT_SMP_SC_PAIR_ONLY` alone
only disables legacy pairing and is insufficient to require authentication.
Disable fixed passkeys, debug keys, storage of debug keys, insecure test entropy
and automatic oldest-bond replacement. These distinctions are present in the
[pinned SMP configuration](https://github.com/zephyrproject-rtos/zephyr/blob/413b789deb391d3a37d06b463288a5fe765ee57e/subsys/bluetooth/host/Kconfig).

`pairing_accept` is synchronous: inspect the current physical-window generation,
deadline, selected connection and admissible security features, then return
immediately. Do not wait for a user, scan NAND or print blocking UART output in
that callback. `passkey_display` publishes only the stack-generated dynamic
six-digit passkey to the physically trusted UART, zero-padded. A bounded event
must retain the matching connection/window generation; inability to deliver it
closes the attempt. The user enters that passkey in Android's system pairing
dialog. Do not derive it from the owner key, use a constant or send it over BLE.
Provide the required `cancel` callback and invalidate stale display events.
These callback obligations are specified in the
[Zephyr authentication callback API](https://docs.zephyrproject.org/4.2.0/doxygen/html/structbt__conn__auth__cb.html).

Check actual L4 and key length in `security_changed`; requesting L4 or receiving
`pairing_complete` alone is insufficient. Timeout, cancel or pairing failure
must discard the attempt and close an unauthenticated connection. Successful
pairing consumes the window immediately. An already authenticated bond may
reconnect at L4 outside this window, but still needs a new ASC1 proof. Any new
pairing/re-pairing attempt outside the window is refused, and bond loss is never
an instruction to reset ownership or overwrite a key.

The physical UART passkey is an initial development interaction, not the final
necklace UX. No automatic passkey entry, acceptance bypass or production
enrollment claim is part of this version. Pairing availability and radio denial
of service remain possible; this protocol does not promise proximity or prevent
a malicious authorized key holder from reading authorized data.

## Required provider and integration checks

The portable provider needs bounded context validation, challenge generation,
split-proof admission, complete verification, confirmation construction,
monotonic-time checks and revoke/clear APIs. Its randomness and clock come from
explicit trusted providers; deterministic test values never become production
defaults. It must perform no NAND I/O, allocation, enrollment or transfer calls.
The serialized integration owns activation and immutable snapshot publication.
Outputs remain unchanged on validation failure, and private/output aliases must
be rejected before copying where the public API admits caller-owned buffers.

Required tests include independent HMAC vectors; each challenge/context/domain/
proof/confirmation byte changed; missing domain NUL; roles reflected; proof
halves reordered, truncated or retried; same nonce under distinct server nonce
and generation; cross-connection and post-reboot replay; exact deadline boundary,
clock/overflow failure, randomness failure, and revoke at every state. Integration
tests must also cover queued LAST followed by revoke, owner-activation failure,
ASNO versus ASOK, pinned long-read snapshots, expired duplicate retries, full
queues, stale passkey/security callbacks, L2/L3 rejection and failed/dynamic L4
pairing inside/outside the physical window. Host cryptographic checks cannot
substitute for executed SMP pairing or physical radio/capture validation.

## Review source pin

Reviewed Zephyr 4.2.0 checkout: `413b789deb391d3a37d06b463288a5fe765ee57e`.
These SHA-256 values identify the existing inputs reviewed for this contract,
not a certificate for a future provider or final firmware build.

| Input | SHA-256 |
| --- | --- |
| `firmware/a04/include/aura_release_auth.h` | `57c5b9c03b2ad739c507706863d3444c017644330af65a3f4a9e3a0e868acd01` |
| `firmware/a04/src/aura_release_auth.c` | `0bf2ad87c2151d5f6ef2adc809ab25b11876d63aa1cad385d004adaedf758fe3` |
| `firmware/a04/RELEASE-AUTH.md` | `86c909940322160d20d1a11796ac08c1f32e623e11d4989c591ab90d01f82f7d` |
| Zephyr `include/zephyr/bluetooth/conn.h` | `904eb2a54b95b3b26465074a2257bce426bc17ffe53d7821c583f73ad8e0e455` |
| Zephyr `subsys/bluetooth/host/Kconfig` | `3290c3cf630a160efcaa8296f370262ff036eceb91a89b3558c113b8b2e510e4` |
| Zephyr `include/zephyr/random/random.h` | `537818cfb0d016c8fc9bdd65063fd5d7b7c6ef12c1644a577ac17632c86d5602` |
