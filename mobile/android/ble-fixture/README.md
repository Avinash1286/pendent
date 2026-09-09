# Android Bluetooth verification fixture

This public, synthetic Python peripheral exercises the real Android GATT client
through Google's Bumble stack and the Android emulator's Netsim controller. It
serves only the two hash-pinned C-generated finalized and physical-OPEN archives.
It does not run the Zephyr transfer engine, authenticate ownership, record audio,
erase data or connect to a physical radio. The consumer enrollment gate remains
separate from this explicit test fixture.

Use Android API 33 or newer for the explicit `suite=virtualBle` mode of the
registered `SmokeInstrumentation` runner. `BleInstrumentation` supplies the
isolated Bluetooth checks through that runner's attached Android context. The
preserved API29 emulator is for the local storage/decoder suite; emulator BLE is
supported on API31+ and the test uses the public API33 random-address constructor.
The separate `AuraApi34Ble` setup and installed dependencies are recorded in
[ble-toolchain.json](../verification/ble-toolchain.json). The SDK repository labels
the downloaded image revision4 while its actual archive properties register
revision2; the evidence preserves both values and their hashes.

## Reproduce on Windows

Install the isolated dependency environment without modifying the companion or
firmware environment:

```powershell
uv venv --python 3.12 .tools/android/bumble-venv
uv pip install --python .tools/android/bumble-venv/Scripts/python.exe --require-hashes -r mobile/android/ble-fixture/requirements-hashed.txt
.tools/android/bumble-venv/Scripts/python.exe mobile/android/ble-fixture/peripheral.py --check
```

The hashed lock describes the verified Windows x86-64 dependency set. Start the
separate API34 AVD with Bluetooth emulation enabled and identify its current
Netsim `grpc.port`; the HCI TCP port is a different interface. Enable Bluetooth
on that explicitly selected emulator. Build both APKs first using the
[Android instructions](../README.md). With the actual emulator serial and gRPC
port substituted:

```powershell
uv run --project companion --locked python mobile/android/scripts/verify_ble.py --serial emulator-5556 --netsim-port 12345 --mtu 517 --output .tools/android/ble-run-517
uv run --project companion --locked python mobile/android/scripts/verify_ble.py --serial emulator-5556 --netsim-port 12345 --mtu 23 --output .tools/android/ble-run-23 --duration-seconds 300
```

`12345` is a placeholder, not a fixed Netsim port. Every run needs a new output
directory. The runner verifies current build/APK inputs, installs both development
APKs on the explicit emulator, starts its own loopback Bumble child and invokes
the test-only instrumentation. The fixed peer is `AURA-test-only`, static-random
address `F0:F1:F2:F3:F4:F5`; there is no physical scan or pairing operation.
Instrumentation temporarily adopts shell Bluetooth permission and drops it after
its GATT threads exit. Bluetooth permissions are declared in the debug manifest,
and the consumer Activity exposes no unauthenticated device access.

The fixture advertises the A04 service and requires subscription before commands.
It preserves exact SELECT/FINISH metadata from C vectors while constructing
HELLO/LIST/READ replies in Python. It checks transaction ordering, exact retries,
complete-record first-read offsets, sequential reads and an explicit zero-byte
EOF read before FINISH. This last constraint exercises the real C cursor's seek
requirement without claiming to execute that cursor inside the fixture.

The runner requires successful Android terminal status, successful exact-source
library imports on two passes, the requested negotiated MTU in the peripheral
record, source stability and a clean child-process exit. It retains failures,
reports, transcripts and file digests. The fixture serves public generated test
signals; real microphones, NAND timing, phone radios, enrollment, charging and
physical wear still require their own tests.

References: [Google Bumble on Android](https://google.github.io/bumble/platforms/android.html),
[Bumble Netsim transport](https://google.github.io/bumble/transports/android_emulator.html),
[Android emulator networking](https://developer.android.com/studio/run/emulator-networking-advanced).
