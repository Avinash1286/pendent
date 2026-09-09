# A04B private bench host

`host.py` is the local UART client for the separate nRF52840 DK application described in [PROTOCOL.md](PROTOCOL.md). It does not flash hardware, discover serial ports, connect Bluetooth, release recordings, erase populated audio storage, repair media, or certify the wearable. The tests use scripted UART bytes and real C-generated archive fixtures; they are not a microphone or NAND bench measurement.

Use the exact wiring and qualification steps in [WIRING.md](WIRING.md) before attaching hardware. The firmware's 60-second autonomous recording limit is a developer bench bound. It is not a product recording limit or evidence of safe battery operation.

## Install and select hardware

Run from the repository root. Python 3.10 or later is required. The client imports the checked-in companion `protocol_v2`, `Receipt`, and `DurableReceiver`; it does not install or modify the companion package. Only actual serial use needs the pinned transport dependency:

```powershell
uv pip install --python .tools/zephyr/venv/Scripts/python.exe -r firmware/a04/bench/requirements.txt
.tools/zephyr/venv/Scripts/python.exe firmware/a04/bench/host.py --port COM7 info
```

Replace `COM7` with the port you have physically identified. On Linux use an explicit path such as `/dev/ttyACM0`. Public INFO discovery reports an unauthenticated device ID. Check the attached DK and copy the full 32-hex ID for subsequent commands. INFO is not a challenge-response authentication protocol; someone controlling the local UART can impersonate it.

Every command that supplies a context or starts recording requires `--device-id`. The host obtains INFO and compares the result before sending the enrollment context. For example, set a task-specific shell variable to the ID you just checked:

```powershell
$auraDeviceId = "PASTE_THE_32_HEX_DEVICE_ID_HERE"
```

Do not replace this with a default identity or a value inferred from an unrelated board. The CLI does not select, auto-flash, reset, or automatically provision a device. Opening a serial port can still affect modem control lines on some adapters; physically validate the intended DK/adapter behavior.

## First enrollment and restart

Keep context, receiver, exports, and temporary recordings in a private local directory outside cloud sync. Repository-local paths are accepted only under the already ignored `.scratch` tree or a `recordings` directory. The examples use `.scratch/privatebench`. Material outside the repository is allowed, but its privacy and backup policy are your responsibility.

```powershell
.tools/zephyr/venv/Scripts/python.exe firmware/a04/bench/host.py --port COM7 --device-id $auraDeviceId --context .scratch/privatebench/context.bin provision
```

Before PROVISION is transmitted, the host creates a CSPRNG storage incarnation, owner ID, and 32-byte owner key; owner generation starts at 1. It creates the exact 88-byte binary context with `O_EXCL`, writes and fsyncs it, and syncs the directory where the platform supports that operation. It never overwrites an existing context. Keep this file: the bench device does not persist the secret key in MCU flash, and OPEN after a restart requires the same authority.

The device accepts PROVISION only against the specified blank-media layout. This reads the complete 128 MiB NAND array. At the bench's conservative 1 MHz SPI setting, the wire-time floor alone is about 18 minutes, with additional command and processing overhead. No INFO response is available during that synchronous scan. PROVISION therefore has a separate 2400-second default deadline, configurable with the global `--provision-timeout` option before the verb. Ordinary requests use a 300-second default `--timeout`. The host never converts a timeout into success or automatically repeats a state-changing command. Keep the exact saved context on timeout and use OPEN to resolve whether provisioning committed.

After a reset, or when a provisioning reply was lost, first attempt:

```powershell
.tools/zephyr/venv/Scripts/python.exe firmware/a04/bench/host.py --port COM7 --device-id $auraDeviceId --context .scratch/privatebench/context.bin open
```

If the host saved the context but died before sending PROVISION, an explicit retry can reuse that exact context:

```powershell
.tools/zephyr/venv/Scripts/python.exe firmware/a04/bench/host.py --port COM7 --device-id $auraDeviceId --context .scratch/privatebench/context.bin provision --resume
```

`--resume` loads the saved context and repeats only the device's blank-media PROVISION operation. It does not reset a ledger, choose different control blocks, regenerate keys, overwrite the context, or recover an incomplete control commit. A populated or uncertain layout fails closed. Retain all context and source material if OPEN and explicit blank-only provisioning both fail.

Context bytes travel in plaintext over the developer UART. Do not collect serial traffic into public logs. The client never prints OPEN/PROVISION arguments, key bytes, raw device error lines, or exception tracebacks. Files created by the host use POSIX mode 0600 and private staging directories use 0700. Windows inherits the parent's ACL; use a directory restricted to your account. Those mode bits alone do not establish a Windows ACL or encrypt a disk.

## Record and inspect

```powershell
.tools/zephyr/venv/Scripts/python.exe firmware/a04/bench/host.py --port COM7 --device-id $auraDeviceId --context .scratch/privatebench/context.bin record --seconds 10
.tools/zephyr/venv/Scripts/python.exe firmware/a04/bench/host.py --port COM7 --device-id $auraDeviceId --context .scratch/privatebench/context.bin list
.tools/zephyr/venv/Scripts/python.exe firmware/a04/bench/host.py --port COM7 --device-id $auraDeviceId stats
```

`record` defaults to 10 seconds and accepts 1 through 60 seconds. It sends OPEN, START, waits the requested interval, then sends STOP. Ctrl+C during the wait makes one best-effort STOP request. A timeout, process kill, or disconnected host can leave recording active until the firmware's autonomous stop; reconnect and LIST rather than assuming the source was finalized. The host sends no acknowledgement or release command after STOP.

STOP output includes the capture ID, audio state, and fault. The terminal audio state values are 4 finalized, 5 interrupted, 6 failed, and 7 quarantined. A valid response with a fault or a state other than finalized returns CLI exit code 2; transport, verification, and local persistence failures return 1. Exit code 0 from record means only that STOP reported finalized with no fault. It is not proof of an imported recording, correct audio, safe electrical behavior, or wearable qualification.

LIST verification values are 0 unverified, 1 verified physical open, 2 verified final, 3 verified physical interrupted, and 4 invalid. A catalog entry alone is not a durable host receipt. STATS prints the actual counters supplied by the connected firmware: maximum service time, late-service count, queue high water, unused reader/storage stack, NAND operation counts, channel peaks, and clipping counts. Counter lifetimes and limitations are defined in PROTOCOL.md; the host does not estimate missing measurements.

## Export, recover and preserve provenance

Copy the capture ID reported by LIST and use an explicit new output bundle and persistent receiver path:

```powershell
.tools/zephyr/venv/Scripts/python.exe firmware/a04/bench/host.py --port COM7 --device-id $auraDeviceId --context .scratch/privatebench/context.bin export CAPTURE_ID_32_HEX --output .scratch/privatebench/exports/first --receiver .scratch/privatebench/receiver.sqlite
```

The host validates exact request IDs, DATA order/offsets, per-chunk CRC, the terminal byte count, the complete AUR3 archive, source identities, and the physical ACK3. An export is limited to 128 MiB. It accepts at most 128 payload bytes per DATA line, 512 bytes per response line, and 64 unrelated lines/8192 unrelated bytes per command. Export has a 10-second inactivity deadline and a separate 7200-second total deadline; `--export-timeout` can change the total bound up to 28800 seconds. Ordinary commands use their bounded command deadline instead of the short DATA inactivity deadline.

The final bundle contains:

- `capture.aura`: the exact verified UART export.
- `physical.ack3`: the exact device-side receipt returned by END EXPORT.
- `metadata.json`: archive hash/size, both receipt identities, physical and exported termination status, and whether the export seal is derived.

For finalized or physically sealed interrupted recordings, the physical receipt must exactly equal the verified archive receipt. For an unsealed physical prefix, the exported archive has a derived interrupted seal. The host independently recomputes the OPEN receipt from the manifest and every packet before that seal. It preserves the distinction in the bundle. The SQLite receiver stores the verified interrupted export; that imported seal is not evidence that the device itself sealed the source, and it is not permission to release it.

Files are first written into a private `.a04b-unpublished-*` directory and fsynced. Only after complete validation and the companion receiver's checked SQLite transaction COMMIT does the host publish the complete bundle. Publication uses a cooperative OS-held lock and a directory rename. Exact retries revalidate the device export, receiver, and all existing bundle bytes. Conflicting existing files are retained and cause failure. The host never replaces a different bundle, truncates an existing receiver, or sends release/delete/erase commands.

A crash after the database commit but before publication leaves the receiver and private temporary bundle; repeat the exact export to finish publication. A lost reply after publication is similarly recoverable by exact retry. Failed and duplicate temporary bundles are intentionally retained; they contain private recordings and must be managed as such. They are not completed downloads merely because bytes exist. Do not feed a partial bundle into the normal source import workflow.

Filesystem durability depends on the OS, drive, and filesystem honoring flushes. POSIX directory entries are fsynced. Python has no supported portable Windows directory-fsync equivalent, so Windows file fsync and atomic directory rename are not a promise of survival through power loss. This client protects against the tested process interruptions; sudden power failure, hostile local writers, device identity authentication, encrypted enrollment, and physical media behavior require separate qualification.

## Reproduce software verification

```powershell
.tools/zephyr/venv/Scripts/python.exe firmware/a04/bench/test_host.py -v
```

The suite covers real C-generated finalized, interrupted and OPEN-prefix archives; request/line/count bounds; CRC, ordering, identity and missing-END failures; timeouts; private context restart and uncertain fsync; explicit provisioning retry without authority replacement; receiver and publication failures; preservation of conflicting artifacts; and real subprocess exits immediately before and after publication. No serial transport dependency or connected hardware is needed for these tests. Passing them does not claim that a microphone, NAND part, assembled PCB, privacy switch, battery, or printed enclosure has been physically tested.
