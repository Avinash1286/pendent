# A04 authenticated Bluetooth DK development application

This separate Zephyr application connects the actual PDM/SPI drivers, Opus
recorder and recoverable NAND storage owner to the A04 archive-transfer service.
It adds a physically opened pairing window and per-connection owner proof.
It targets **nrf52840dk/nrf52840 with external fixtures**, not the AURA PCB.
It has not been flashed or executed on physical hardware.

[Download the DK development package](https://github.com/Avinash1286/pendent/releases/tag/a04-radio-dk-dev)
and read its [artifact scope](DOWNLOADS.md) before using the files.

The [wired bench](../bench/README.md) remains a separate build. This application
uses its [fixture wiring](../bench/WIRING.md) and monitored microphone driver.
The reviewed pin assignment is for that DK fixture only. Neither application
provides battery charging, product controls, signed boot/OTA or a wearable board
definition. Capture is still explicitly started over the local UART and stops
after 60 seconds. The physical privacy input remains required.

## Recording and transfer

The storage thread owns all journal, recorder and transfer calls. Bluetooth
callbacks copy bounded commands; they never scan NAND or encode audio. There is
one connection, one pending command and one immutable notification buffer.
Capture preempts incremental transfer between owner steps and closes new pairing
admission. A completed notification or FINISH response never permits source
deletion. There is no Bluetooth START, DELETE, FORMAT, PROVISION or release API.

The unchanged [transfer wire contract](../../../docs/a04/transfer-wire-v1.md)
provides HELLO, LIST, SELECT, READ, FINISH and CANCEL. The
[adapter](src/aura_gatt_zephyr.c) supports MTU 23 through 517; this initial DK
configuration caps the negotiated ATT MTU at 247 to bound radio buffers.
Authentication uses a separate characteristic and does not consume a transfer
transaction. See the exact [ASC1 contract](../../../docs/a04/session-auth-v1.md).

## Local setup and authentication

UART requests retain the [A04B framing](../bench/PROTOCOL.md):
`A04B <eight-hex-digit request ID> <verb> [argument]`, at 115200 8N1.
Only one host request may be outstanding. The following differences apply:

| Command | Radio application behavior |
| --- | --- |
| `PROVISION` / `OPEN` | Close radio access first, then use the existing physically trusted 88-byte owner context. Successful storage open initializes transfer and proof state. Never send this key-bearing context over BLE. |
| `PAIR` | Requires opened storage and idle capture. Opens a 60-second pairing window, at most three attempts, and enables advertising. Repeating it inside that window does not extend the deadline. |
| `RADIO` | Enables advertising for an existing authenticated bond. It does not open pairing or grant archive access. |
| `RADIOINFO` | Returns `OK RADIOINFO <fault> <enabled> <connected> <L4> <subscribed> <transfer-ready> <generation> <pair-window-open>`. Flags are 0/1; fault is the retained signed Bluetooth initialization/advertising error. This status contains no key or owner proof. |
| `LOCK` | Closes pairing and radio admission, disconnects the current session and forgets the proof provider's context. A fresh local OPEN is required before radio access can resume. It does not erase recordings. |
| `LIST` | Prints catalog metadata only. Bluetooth SELECT performs incremental source verification. |
| `EXPORT` | Unsupported in this target. Use the incremental Bluetooth archive protocol. The wired bench still has its own UART EXPORT. |
| `START` / `STOP` | Local capture controls, with the wired bench's physical permission and terminal-state rules. Starting capture closes pending pairing and preempts transfer. |

Unsolicited pairing events use request ID `00000000`: `PAIR PASSKEY <six digits>`,
`PAIR COMPLETE`, `PAIR CANCELLED` or `PAIR EXPIRED`. The fresh passkey is displayed
only on the physically trusted UART and entered in the phone's system pairing
dialog. Fixed passkeys, Just Works fallback and debug keys are disabled.

Every connection requires actual authenticated LE Secure Connections (L4), a
16-byte link key, response subscription and a fresh mutual ASC1 owner proof.
An authenticated bond alone cannot read the archive. Proof must complete within
30 seconds of BEGIN acceptance; the read-only grant has a ten-minute absolute
deadline from proof acceptance. A separate watchdog and callback admission checks
revoke access even when storage work delays the owner thread. Retries do not
extend deadlines. Large-source completion and renewal still require measurement
and further integration.

The owner key is volatile and must be supplied locally after reset. The isolated
32 KiB internal-NOR settings partition holds Bluetooth identity/bonds/CCC only;
it is **not protected owner-key storage**. There is no consumer enrollment or
ownership-reset flow. A hostile local host/debug probe is outside this initial
trusted-UART arrangement.

## Build and verify

From the repository root with the existing pinned tools installed:

```powershell
pwsh -NoProfile -File firmware/a04/radio/build.ps1 -Mode arm -Jobs 2
.tools/zephyr/venv/Scripts/python.exe -B firmware/a04/radio/verify_session_auth.py
.tools/zephyr/venv/Scripts/python.exe -B firmware/a04/radio/tests/run_gatt.py
.tools/zephyr/venv/Scripts/python.exe -B firmware/a04/radio/tests/pairing_stub/verify.py
```

Build products stay under `.tools/a04-radio/arm`; the build script performs no
flashing or radio operations. The linker confines the standalone DK image to
`0x00000000..0x000f7fff`; BT settings occupy `0x000f8000..0x000fffff`.
This layout has no bootloader/OTA slots. The 48 KiB storage/codec stack and 4 KiB
reader stack remain reserved; their runtime headroom is not measured.

The [final ARM resource report](verification/arm-resources.json) records
**432,020 bytes FLASH** and **243,652 bytes RAM**, leaving **18,492 bytes RAM**
unallocated. It binds 61 source inputs, the 482 pinned Opus files and 159
generated files. GATT state occupies 1,768 bytes, the proof provider 376 bytes,
pairing state 168 bytes and the transfer owner 4,440 bytes. The audio object is
21,072 bytes: Bluetooth selects Zephyr `CONFIG_POLL`, adding an eight-byte event
list to the embedded message queue. This is a verified ABI difference from the
wired bench; audio buffers and thread stacks were not reduced.

The retained attempt logs include the corrected advertising-declaration compile
failure and a successful link followed by an overly strict ABI-report check.
The final source-bound inspection passes. The compiling attempt also retains
upstream Opus diagnostics and six warnings in existing shared modules; the new
main/GATT/pairing sources compile with warnings treated as errors. This is not
a warning-free whole-dependency build. The report's static stack analysis is
not measured runtime headroom or a radio/audio continuity result.

The [GATT host report](tests/gatt-host-tests.json) currently covers 18 groups
using the actual adapter and actual portable transfer/journal code with modeled
Zephyr, clock and radio boundaries. It covers stale callbacks, inline completion,
resource exhaustion, capture preemption, subscription/security loss, independent
expiry and MTU 23/247/517 fragments. These tests do not execute the Zephyr kernel,
SMP or a physical radio.

The [portable proof report](verification/session-auth.json) covers 12 groups /
13,726 C checks plus 18 independent Python HMAC checks. The
[pairing-policy report](verification/pairing-host.json) covers nine groups /
513 checks against actual callbacks with modeled clocks, registration and
connection references. Keys and nonces in these vectors are public test data,
never enrollment defaults. Neither report establishes physical SMP, the
platform's asserted link security or secret custody.

## Next integration gate

The [published Android development app](../../../mobile/android/README.md)
already has a real GATT transport and durable recovery owner, tested against a
virtual Bumble peripheral. That fixture does not implement ASC1 or execute this
firmware. The app needs the matching proof exchange, trusted owner-context
custody and consumer connection UI before it can access this new radio target.
Do not interpret the older virtual tests as an Android-to-Zephyr pairing result.

The next physical test is the matched DK microphone/NAND fixture: pair at L4,
complete owner proof, record a spoken note, download and independently decode it,
then interrupt and recover transfer. Measure PDM latency/FIFO loss, flash and
internal-NOR settings stalls, concurrent-radio stack headroom and current.
Neither host checks nor an ARM link replace that experiment. Follow the full
[first-wearable gates](../../../docs/research/aura-first-wearable.md) before a
custom board, powered enclosure or wear trial is accepted.

The authored radio/session/pairing code is MIT. The image statically links Opus,
Zephyr, Nordic HAL/CMSIS, Mbed TLS PSA and the SDK C/compiler runtime. The
development package retains [firmware notices](../../THIRD_PARTY_NOTICES.md),
[A04/Opus notices](../THIRD_PARTY_NOTICES.md) and their license texts. The older
A04 notice describes its Bluetooth-disabled probe; this separate target enables
Bluetooth and Mbed TLS PSA as recorded in its resolved build configuration.
