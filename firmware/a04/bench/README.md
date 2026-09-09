# AURA A04: first spoken-note bench

This separate **nRF52840 DK** application connects the actual A04 audio, Opus and NAND-storage code to physical peripheral drivers. It provides a local UART tool for explicit recording and verified export. It has been cross-compiled and tested with deterministic host fixtures. **No DK has been flashed, no microphones or NAND have been exercised, and no physical recording has been made.**

This is the executable software for [the first wearable plan's audio/storage gate](../../../docs/research/aura-first-wearable.md). The AURA PCB remains unplaced and unrouted. This firmware is not its board definition and must not be flashed to AURA, an Omi board, or a different development kit.

## What the bench does

- Keeps microphone power off at boot. A START command and the physical allow contact are both required. The physical switch also interrupts the microphone load-switch enable path.
- Reads two PDM channels into the monitored, bounded audio queue; averages them to mono; encodes 16 kHz audio with the existing 20 ms Opus profile; stores complete records in real W25N01GV through the serialized storage owner.
- Stops at the host's requested 1–60 second duration, with an autonomous 60-second limit. Ordinary STOP finalizes only after healthy producer quiescence and FIFO drain. Privacy cutoff, lost audio, and uncertain storage remain explicit failures or interruptions.
- Recovers an existing journal after the host supplies the same saved enrollment context. Exports exact audio with its physical receipt. The host independently checks the archive and commits its local receiver before publishing a complete bundle.
- Reports capture service time, FIFO occupancy, unused thread stack, NAND operation counters and per-channel peaks/clipping. These become measurements only when the image runs on hardware.

There is no Bluetooth, battery/charger integration, automatic formatting, audio-release command, signed update, or secret persisted in MCU flash. UART enrollment is plaintext and requires an explicitly selected local device. The [protocol](PROTOCOL.md) and [host guide](HOST.md) define these boundaries.

## Reproduce the build

Run from the repository root. The existing installer supplies the pinned Windows Zephyr 4.2.0, SDK 0.17.2 and host tools. The bench build verifies the unmodified Opus 1.6.1 dependency and uses a separate output directory.

```powershell
./firmware/scripts/setup.ps1
./firmware/a04/bench/build.ps1
```

Use `-Mode host` for the UART and C orchestration suites, or `-Mode arm` for the target build and ELF/devicetree report. Neither command opens a serial port or flashes hardware. Outputs are under `.tools/a04-bench/arm/zephyr/`; do not confuse them with the parent integration probe under `.tools/a04-opus/arm/zephyr/` or the A03 firmware.

The new bench command/controller source (`src/main.c`) compiles with warnings treated as errors. Shared legacy source and the unmodified Opus dependency still produce compiler diagnostics recorded in the initial build transcript; a successful link is not a warning-free or runtime qualification claim. The [ARM report](verification/arm-resources.json) records actual linked reservations, memory use, configuration, pins and source hashes. Per-function compiler stack reports are lower bounds; Opus uses dynamic stack allocation and needs runtime measurement.

## Assemble and connect the fixture

Follow the full [wiring and component review](WIRING.md) before applying power. The named microphone route is one KAS-700-0164 two-pack of **SPH0641LU4H-1**, with two KCA2733 adapters. It matches the A04 microphone choice. Use a real W25N01GVSFIG on a passive SOIC16 adapter, the specified microphone load switch, clock buffer and linked privacy contacts. The DK's onboard QSPI NOR is a different part and cannot substitute for it.

Use the reviewed common DK VDD/GND rail and check the actual board revision, pin continuity, polarity, rail levels and current first. Keep this experiment USB/external powered and off body. The calculated DATA margins, physical switch behavior, clock integrity and power-off backfeed boundaries still require the measurements listed in WIRING.md.

The compiled pin assignment is PDM P0.30/P0.31; SPI3 P1.15/P1.13/P1.14 with CS P1.12; microphone enable P1.03; privacy sense P1.04; onboard LED P0.13. UART0 retains the interface MCU's existing pins. The actual adapter requests **1.280 MHz PDM with 80× decimation for 16 kHz PCM**; NAND SCK is independently 1 MHz. Do not substitute a 1.000 MHz PDM clock. Initial firmware configuration is evidence of intent; measure the physical waveforms and decoded sample rate.

Flashing is an explicit physical step after the unpowered checks. Use the matching nRF52840 DK's identified debug probe and the generated bench `zephyr.hex`, with the runner specified by the generated `runners.yaml`. Inspect the installed runner's help and select the probe explicitly; do not use a connected-device default or mass-erase command. The build script deliberately does not perform this step. Flashing replaces the selected DK's MCU application; external NAND is handled only by the separate explicit commands below.

## First recording and recovery

The [host guide](HOST.md) provides complete copyable commands and recovery behavior. Its sequence is:

1. Install the pinned pyserial dependency, open the physically identified UART port and run public INFO. Check the full device ID before using it as the expected identity.
2. On an explicitly empty test NAND, run PROVISION with a new private context path. The host saves the exact random context before transmission. Keep it across resets. First provisioning scans the full 128 MiB array: at 1 MHz SPI its wire-time floor alone is about **18 minutes**, plus overhead. The separate default deadline is 40 minutes. A timeout is uncertain, so retain the context and use OPEN to resolve it.
3. Enable the physical allow switch, record ten seconds of clear speech, and inspect the terminal status. Record the STATS output before another START resets its capture counters.
4. LIST, then EXPORT the exact capture ID into a new private bundle and persistent receiver. The bundle contains `capture.aura`, `physical.ack3` and `metadata.json`. Only a verified complete bundle is an accepted transfer; STOP and LIST alone are not receipts.
5. Use the existing [A04 companion archive importer](../../../companion/README.md#a04-archive-import--040) to inspect/reconstruct audio, independently decode it and listen. Check intelligibility, duration, clipping and source identity. Synthetic codec fixtures are not substitutes for this listening test.
6. Reset the DK, OPEN with the identical context and export again to confirm byte-identical recovery. Then use a separate disposable test recording for deliberate disconnect/power-interruption trials. Recover the verified prefix with an explicit interrupted status; never rename it a finalized recording.

Do not erase unknown NAND contents to make enrollment pass. The bench does not release populated audio, so accepted captures remain on the device. At the journal's 128-capture bound, or when storage is full or quarantined, stop and preserve the sources. Capacity reclamation and a responsive phone product flow are later integrations, not hidden bench features.

## Physical acceptance log

Make 20 spoken-note trials with distinguishable voices/sounds at documented distance and orientation. For each, retain the exact board/part/firmware revisions, private source/export, terminal status and runtime counters. Decode and play back every accepted note. Test each microphone separately to establish channel wiring before judging the averaged signal.

Measure service deadlines, FIFO loss, runtime stack headroom, supply current, mic cutoff/backfeed, NAND latency and clock/data integrity under the actual workload. STATS supplies aggregate observations; isolate codec and NAND timing with separate instrumentation before assigning a slowdown to either. Compare current and timing against a stated workload, not an assumed battery-life claim.

Keep recordings and context files under the ignored `.scratch/privatebench` path or another private, unsynced location. Publish only sanitized measurements. A successful bench gate permits the next phone and board-integration work; it does not qualify battery charging, RF near skin, enclosure comfort, fabrication, or wearing a powered custom unit.

## Software evidence

- [UART host suite](verification/host-tests.json): actual C-generated archives, complete receipts, bounded scripted serial input, private-context recovery, SQLite/publication failures and process termination around publication.
- [C orchestration suite](tests/control-report.json): actual bench `main.c`, actual audio adapter and archive CRC/SHA, with bounded recorder/storage/driver/Zephyr doubles. It covers startup cancellation, normal and physical STOP, terminal-seal error reporting, RX framing and export receipt ordering.
- [ARM resources and pins](verification/arm-resources.json): actual ARM ELF and generated devicetree, with immutable input hashes. These are cross-build checks, not device execution.
- [Wiring evidence](wiring-review.json): named parts, primary datasheets and checked local pin-map sources, with remaining electrical measurements.

The broader [A04 firmware evidence](../README.md) covers real Opus encoding/decoding, NAND fault models and authenticated release/reuse tests independently of this bench harness. No host model supplies physical first-article evidence.
