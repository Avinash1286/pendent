# AURA A03 firmware

An actual Zephyr application for the **Raytac MDBT50Q-1MV2 / nRF52840** on the A03 PCB. It records without a phone, saves recoverable audio to W25N01GV SPI NAND, and serves recordings over encrypted Bluetooth to the [companion](../companion/). This firmware does not run transcription or an LLM on the pendant.

This is engineering firmware, not a claim of tested physical hardware. The release image keeps charging permission and haptics disabled until the assembled battery, thermistor, charger and motor are qualified. The application, host tests, board source and resulting ARM artifacts are included for reproduction and bring-up.

## Build and flash

The tested Windows toolchain is Zephyr **v4.2.0** (`413b789deb391d3a37d06b463288a5fe765ee57e`), Zephyr SDK **0.17.2**, ARM GCC **12.2.0**, Python **3.12**, West **1.4.0**, CMake **3.31.6** and Ninja **1.11.1.4**. Setup downloads official pinned Zephyr modules and verifies SHA-256 hashes of the SDK archives. It needs Git, `uv`, Windows `tar` and `curl` on PATH. Tools and intermediates go in the repository's ignored `.tools/zephyr` directory.

From the repository root in PowerShell:

```powershell
./firmware/scripts/setup.ps1
./firmware/scripts/test.ps1
./firmware/scripts/build.ps1
```

The default build writes `release/aura-a03.hex`, `.bin`, `.elf`, `.map`, `build.config` and a SHA-256 manifest. HEX includes absolute MCU flash addresses; raw BIN starts at address `0x00000000`. ELF retains debugging information. The final 32 KiB of MCU flash is reserved for Bluetooth bonds and maintenance state. Do not mass-erase that partition during an interrupted storage format: its erase-intent marker protects recovery.

Connect a compatible SWD probe to J3: pad 1 target-reference 3.0 V, pad 2 SWDIO, pad 3 SWCLK, pad 4 RESET, pads 5/6 GND. A probe's target-reference input is not necessarily a power output. Use the reviewed current-limited supply arrangement during bring-up. With SEGGER J-Link and its software installed:

```powershell
$env:PATH = (Resolve-Path .tools/zephyr/venv/Scripts).Path + ';' + $env:PATH
west flash -d .tools/zephyr/build-aura --runner jlink
```

SWD flashing is implemented; signed boot, authenticated DFU and debug locking are not. Do not ship this image as a consumer security release. Reproduce on Linux/macOS by using the same Zephyr commit/modules and matching host SDK, then `west build -b aura_a03/nrf52840 firmware`; the included automation is Windows-specific.

## What the code does

| Area | Implemented behavior |
|---|---|
| Capture | Two interleaved PDM channels, arithmetic mono mix, PCM16 LE output at 16 kHz. Audio runs in its own thread with eight DMA buffers. |
| Clock | Module LFRC with Zephyr calibration. PDM is constrained to 1.280 MHz (32 MHz / 25) and Zephyr selects RATIO80, producing exactly 16,000 input samples/s. This falls within the microphone's standard-mode clock range. No resampling is needed. A 50 ms rail delay plus two discarded 40 ms DMA blocks allow microphone/decimator startup. |
| Gesture | Debounced face paddle; single press starts/stops after a 300 ms double-press window; double press while recording journals a bookmark; idle three-second hold opens pairing for 60 seconds. Ten-second hold opens maintenance permission for 30 seconds. |
| Privacy | OFF is P1.08 HIGH. The switch physically removes microphone power; a GPIO interrupt also drops microphone enable. Firmware never exposes a remote start command. The amber indicator is powered by the microphone rail. |
| Storage | Correct SPI NAND commands, JEDEC `EF AA 21` check, internal ECC, factory bad-block scan, readback after every page program, CRC-protected page journal and interrupted-note recovery. No overwrite of unique audio. |
| Transfer | Encrypted GATT, long reads, per-chunk CRC and full-record CRC, exact size/CRC deletion guard. Only completed or recovered notes are listed. The peripheral requests MTU 247; default-MTU clients can still use long reads. Stop recording before transferring audio. |
| Reuse | Explicit maintenance erase after all notes were explicitly deleted; MCU NVS intent guarantees interrupted erase resumes before notes become visible. Recording ID floor persists across maintenance. |
| Power | MAX17048 voltage reads, start threshold 3.5 V, active-record stop below 3.3 V or on gauge failure. Microphones are gated outside capture. Charger permission is default LOW, with a separate hardware hot cutoff. |
| Watchdog | 8-second reset watchdog after storage recovery; feeds require audio-thread progress. Privacy remains physically independent. |
| Haptic | Optional C08-00A initialization and auto-calibration, reduced engineering voltage targets, short RTP pulse. Disabled in the distributed image until measured qualification. |

At 32,000 PCM bytes/s, the ideal capacity is about **66 minutes** before note/marker overhead, factory bad blocks and reserve pages. This is an arithmetic upper bound, not measured endurance or battery runtime. At most 128 journaled note IDs are indexed per maintenance cycle, including deleted notes. Deletion hides a note and appends a tombstone; storage capacity returns only after the explicit maintenance erase. This conservative implementation does not claim wear leveling or online garbage collection.

Bookmarks are preserved as byte offsets in journal records. Protocol v1 does not yet export bookmark records; the transferred WAV contains the audio only. Time is set by the companion and advances from uptime. Before time synchronization, timestamp zero means unknown. Time does not survive full power loss; recording IDs and committed audio do.

## Pin map

| Signal | MCU pin | A03 function |
|---|---|---|
| PDM clock / data | P0.04 / P0.05 | Dual PDM microphones through Ioff buffer |
| Microphone enable | P0.06 | HIGH permits recording regulator |
| Record paddle | P0.08 | Active LOW |
| Privacy OFF | P1.08 | HIGH means microphones OFF |
| SPI MOSI / MISO | P0.14 / P0.13 | NAND |
| SPI SCK / CS | P0.16 / P0.15 | NAND, mode 0, 8 MHz |
| I2C SCL / SDA | P0.27 / P0.26 | MAX17048 at 0x36, DRV2605L at 0x5A |
| Haptic enable | P0.17 | Default LOW |
| Gauge alert | P0.19 | Routed; baseline polls voltage |
| Charge status 1 / 2 | P0.21 / P0.20 | Routed; not interpreted by baseline UI |
| Charge permission | P0.23 | HIGH only permits the independent thermal gate |
| Reset | P0.18 | SWD reset |

The authoritative circuit is [hardware/src/design.ts](../hardware/src/design.ts). The custom board does not inherit development-kit LEDs or UART pins that collide with NAND. There is no external LF crystal in this assembly.

## Storage and power-loss behavior

Each 2,048-byte NAND page contains a 40-byte header and up to 2,008 bytes of payload. A header identifies revision, record type, note ID, PCM offset, payload length, time, expected record CRC and flags. CRC32 covers the first 36 header bytes plus payload. Types are START, DATA, END, DELETE and MARK. Each page is programmed once and read back. The first two pages of every block remain unused so manufacturer main-area and spare-area bad-block markers stay intact.

Boot scans every usable page; an erased hole is not assumed to be the end of data. START creates an index entry. Contiguous valid DATA pages extend its size and CRC. A valid matching END commits it. Missing/torn END or last DATA page leaves a recovered note containing prior valid pages, flagged as interrupted. Uncorrectable ECC returns an error; the code does not silently recalculate a new CRC and pretend corrupted committed audio is intact. Runtime program/read failures stop capture and retain recoverable data. Faulty used blocks are not erased or remapped while they may contain unique audio.

The scan and full maintenance verification read the entire device and may take minutes; startup currently favors conservative recovery over instant readiness. Storage speed, read disturb, wear distribution, new bad-block retirement and crash injection on real NAND remain release work. Do not rely on this prototype as the sole copy of irreplaceable recordings.

READ is rejected with FORBIDDEN while capture is active or starting. This prevents a distant random seek from holding the NAND mutex long enough to exhaust audio DMA buffers. During a permitted read the unit briefly reports saving/busy and does not accept a new capture. Sequential requests retain a page cursor. An interrupted long seek can be retried after the previous command completes; no audio is deleted by a read timeout.

## Bluetooth and maintenance

The exact base contract is [docs/ble-protocol.md](../docs/ble-protocol.md). A03 adds opcode **6 FORMAT**, request payload little-endian `u32 0x53415245` (bytes `ERAS`), empty successful response. It is forbidden unless the unit is idle, every recording has a committed explicit-delete tombstone, and the user held the face paddle for ten seconds within the previous thirty seconds. Each attempt consumes that permission. Normal command timeout is 30 seconds; FORMAT may need up to 600 seconds while erasing and verifying every usable block. A disconnect does not cancel an accepted format. If power fails, reconnect after recovery; do not automatically resend a destructive command.

Before any erase, the MCU's NVS stores the next-ID floor and durable format intent. Recovery checks this state before mounting/exposing NAND notes. A failed/interrupted erase leaves intent set and resumes on reboot. Completion clears intent only after all good blocks were erased, read back and mounted as an empty journal. Bonds are preserved. Factory-bad blocks are skipped. This is not a cryptographic secure erase: data remnants in bad NAND blocks may remain.

Only physically opened pairing windows allow new Secure Connections bonds. Otherwise advertising uses the bonded-address accept list. The device has no display and uses Just Works association, so encryption is **not authenticated MITM protection**. Audio at rest in NAND and bond secrets in MCU flash are not protected against physical extraction. Secure boot, at-rest authenticated encryption, provisioning, debug lockdown, signed updates and a defined factory-reset policy are still required for a consumer release.

## Charging and haptic qualification

The distributed `prj.conf` intentionally has both `CONFIG_AURA_CHARGE_QUALIFIED=n` and `CONFIG_AURA_HAPTIC_QUALIFIED=n`. This image will not recharge a battery or vibrate. Its recording/transfer functions can be brought up with a reviewed, current-limited supply or already charged qualified pack. A deliberately separate configuration enables these paths:

```powershell
./firmware/scripts/build.ps1 -QualifiedHardware
```

That command builds into `build-aura-qualified`; it does not replace the default distributed release. Enable only after completing the following measurements and saving their evidence:

1. Confirm exact protected-pack dimensions, 4.221 V maximum charger acceptance, allowed peak system current and NTC attachment. Scope P0.23 LOW through boot/reset/brownout and the comparator-valid delay. Review [thermal-review.md](../docs/thermal-review.md).
2. Measure charge current and terminal voltage. Inject open/short NTC and hot/cold conditions in the closed enclosure. Confirm the independent TLV6700 path prevents firmware from overriding the hot stop. Confirm stable adapter-mode TS bias and thermal lag.
3. Verify depleted-cell startup from SYS and recovery through the qualified voltage range. The baseline inhibits charging if gauge reads fail or reports below 2.0 V/above 4.25 V; pack protection and BQ precharge/recovery behavior require bench verification. Do not defeat that guard to recover a damaged cell.
4. Verify the exact C08-00A variant, motor wiring, 240 Hz resonance and DRV2605L auto-calibration. The candidate is rated 1.2 Vrms, maximum 1.25 Vrms; source targets approximately 0.84 Vrms with a conservative clamp. Scope RMS and peak waveform throughout calibration and RTP playback; register arithmetic alone is not a voltage measurement. Qualify comfortable pulses and enclosure acoustics before enabling feedback.

## Verification and remaining bring-up

[verification/host-tests.txt](verification/host-tests.txt) records 14 actual native test cases using the same journal, gesture, PCM mixer and maintenance C code used in the firmware. Cases include known CRC vector, cross-page read, wrong delete metadata, missing END, torn program, uncorrectable ECC, bad block skip, capacity reserve, bounce/hold/double press, signed PCM mixing and interrupted erase. [verification/nand-tests.txt](verification/nand-tests.txt) adds four cases executing the production NAND serializer against a strict simulated SPI chip: JEDEC/features/markers, program order/readback, ECC/program failures and erase verification. These simulations do not test actual SPI silicon, soldering, RF performance or battery.

Bring up in this order: unpowered inspection; current-limited rails; SWD; gauge; NAND ID/features/markers; program/read/ECC injection; microphone OFF leakage and signal back-power; actual PDM timing and acoustic capture; repeated unplug during DATA/END/DELETE/FORMAT; BLE pairing/bond persistence and interrupted long reads; qualified charging and haptics; closed-enclosure thermal/RF/acoustic/ESD testing; measured sleep/capture/sync endurance. Verify the transfer/capture mutual-exclusion policy under rapid button presses and incoming requests. Run stack high-water instrumentation and long recordings before accepting the 4 KiB audio thread stack.

## Sources and licensing

Application code is MIT under the repository license. Zephyr is Apache-2.0 and includes separately licensed modules; the release links Nordic HAL, Mbed TLS and the SDK C library under their upstream terms. The setup pins upstream sources instead of checking third-party SDK binaries into GitHub. Release notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

- [Zephyr 4.2.0 source and sample](https://github.com/zephyrproject-rtos/zephyr/tree/v4.2.0/samples/drivers/audio/dmic)
- [Zephyr SDK 0.17.2](https://github.com/zephyrproject-rtos/sdk-ng/releases/tag/v0.17.2)
- [Winbond W25N-GV official product/documentation](https://www.winbond.com/hq/product/code-storage-flash/qspi-nand/w25n-gv/index.html?__locale=en)
- [MAX17048 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX17048-MAX17049.pdf)
- [DRV2605L datasheet](https://www.ti.com/lit/ds/symlink/drv2605l.pdf)
- [BQ25185 datasheet](https://www.ti.com/lit/ds/symlink/bq25185.pdf)

