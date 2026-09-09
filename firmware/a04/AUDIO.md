# A04 microphone ingress and capture ownership

Status: **implemented integration code under host and DK cross-build verification; no physical AURA recording or timing qualification**. The A04 PCB pin map remains incomplete. The separate A03 firmware and release artifacts are unchanged.

The input path now has a monitored PDM driver, a bounded producer FIFO and one recorder/storage owner:

```text
two PDM microphones → nrfx DMA → monitored DMIC queue
                                      ↓ reader task
                              16-block mono FIFO
                                      ↓ storage task
                           Opus → AUR3 → NAND journal
                                      ↓ verified export
                           desktop receiver → notes
```

The [driver](drivers/README.md) is a local adaptation of the pinned Zephyr 4.2 driver, with its upstream notices retained. Its sticky faults and ownership counters address failure information the original driver did not expose. Application sequence numbers alone cannot detect an overflow that occurred before a buffer reached the application. This project does not patch the installed Zephyr checkout.

## Ownership and scheduling

[aura_audio_zephyr.h](include/aura_audio_zephyr.h) exposes two steps, not hidden background work. The embedding application must create a higher-priority reader task calling `aura_audio_zephyr_reader_step` and a lower-priority storage task calling `aura_audio_zephyr_service`. Only the storage task may call `begin` or use the recorder, codec, archive and journal. The reader never encodes or accesses NAND. Normal-stop and privacy requests may arrive concurrently; all other lifecycle transitions have one application owner. Initialize the adapter once, with no active device or pending capture; never overwrite a live object.

The adapter owns eight 1280-byte stereo DMA slab blocks and a sixteen-entry FIFO. Each FIFO entry holds 320 mono samples plus epoch, sequence and source offset. At the nominal 16 kHz rate this is 320 ms of application FIFO capacity, excluding driver buffering. It is a finite reservation, not a measured guarantee that all flash stalls fit. A full FIFO stops input and causes an interrupted capture. It never overwrites old entries.

The storage owner consumes each message once. [The recorder](RECORDER.md) reports exactly how many samples were consumed on a failed call; the adapter releases that message and ends the capture instead of feeding its consumed prefix again. Frames already copied into the application FIFO are drained before interruption is sealed. Driver buffers implicated by a sticky fault are conservatively discarded and freed. A new capture requires a fresh ID and increasing nonzero session epoch.

The storage step must continue to run while starting and stopping, including when no audio is queued, so the journal's serviced deadline can flush accepted records. Use the codec's required stack and measure stack high-water, CPU deadlines, scheduling latency, flash latency and BLE interference on silicon. The DK resource probe reserves its codec stack but is not a complete two-thread product scheduler.

## Start, stop and privacy

Start prepares the mounted journal and begins the recorder before enabling microphone power. Configuration is restricted to stereo PCM16, one stream, a 1.28 MHz PDM clock and a requested 16 kHz rate. The actual returned channel map must match. A dedicated native GPIO starts inactive; there is no hard-coded AURA pin assignment in the adapter.

Power settling takes a provisional 50 ms. The reader then discards four complete clocked blocks, nominally 80 ms, before publishing usable PCM. These conservative startup allowances require microphone/decimator measurements and can affect first-syllable UX. The capture timestamp remains explicitly unknown: a button/request timestamp must not be advertised as the first usable sample through that startup delay. The first published sample is source offset zero.

A normal stop accepts a complete block boundary, stops the peripheral, drains completed queued buffers and frees their slab storage. It may finalize only after the driver reports stopped and drained, no DMA or caller slab ownership remains, and the application FIFO is empty. The final producer sample watermark must match the recorder's accepted source count. The partial in-flight DMA tail is discarded by the driver; a finalized archive describes the exact accepted source interval, not an assertion that every sample through the physical button instant was retained.

A privacy cutoff immediately drives the native microphone-enable GPIO inactive, latches an interrupted-capture request and leaves source preservation to the storage owner. The GPIO-on decision and cutoff use a short IRQ-safe critical section on the single-core nRF52840; they must not use a blocking GPIO expander. Monotonic request generations prevent a concurrent stop/privacy request from being erased by startup state reset. The separate physical switch must disconnect the microphone rail independently of firmware. Software tests do not prove that electrical path.

The final driver-health/cutoff check, nonblocking FIFO copy and source-watermark update share a short IRQ-locked section. A cutoff before that publication discards the block; one delivered after it can retain that already-published block. PCM conversion and the application permission callback run outside the critical section. Measure its interrupt latency on silicon; the host suite models ordering, not timing.

Reads have a 100 ms timeout. Asynchronous stop cleanup is polled without blocking reads, with a 250 ms deadline. A timeout quarantines the adapter, cuts its software power request and prevents restart. It does **not** grant permission to recycle memory still owned by DMA. Keep the object, slab and device alive until a reviewed recovery procedure establishes quiescence. Sleeping for a fixed time is not that proof.

## Channel interpretation and audio quality

The reader supports first channel, second channel or their bounded arithmetic mean. It records per-channel peak and saturated-sample counts for later calibration. The mean is not beamforming, denoising or automatic gain control. No DC filter, acoustic compensation or channel-quality preference is assumed to be qualified.

With the current schematic SELECT wiring and the default Nordic LEFTFALLING map, the first channel corresponds to MK2 (SELECT high) and the second to MK1 (SELECT low). The schematic's visual Left/Right labels are not sufficient to identify physical channels. Confirm each microphone independently on the actual board. The nRF52840's 1.28 MHz / 80 configuration gives nominal 16 kHz relative to its HF clock; measure actual oscillator/sample-rate error, gain, clipping, phase and enclosure acoustics.

## Build and verification boundary

Run the pinned integrated build from the repository root:

```powershell
./firmware/a04/scripts/build.ps1 -Mode all
```

When migrating an existing generated build from the earlier codec-only probe,
run the ARM subset once with `-Pristine` to re-merge the new driver Kconfig and
devicetree. The script verifies the exact generated A04 ARM build directory
before asking West to clear it. Later builds are incremental.

The ARM target remains **nrf52840dk/nrf52840**, with the explicit [DK test overlay](drivers/probe/nrf52840dk_nrf52840.overlay). It binds P0.30 CLK and P0.31 DIN from the upstream DK sample, uses the custom monitored driver and excludes the competing stock DMIC driver. Boot applies that DK pin configuration. The synthetic probe never enables microphone power or starts a physical PDM stream, SPI NAND operation, radio or charger. **Do not flash this image onto AURA.** Final A04 devicetree, board identity, power controls and production scheduling must come from the corrected native schematic.

The portable recorder tests use the actual codec/archive/journal and real synthetic speech, with independent SQLite restart/replay and FFmpeg decode. Adapter tests compile the actual adapter against bounded kernel/GPIO/DMIC stubs and exercise deterministic task/interrupt interleavings. Driver tests compile the production callback/start/stop/read/health logic with kernel/HAL boundaries mocked. These layers establish different software properties; none is a physical microphone, DMA, power-loss, radio, thermal or wearable test.

Remaining integration includes the actual A04 pin map and hardware execution, persistent device identity and owner binding, complete task scheduling/watchdog behavior, BLE recovery, signed updates, sustainable NAND reclamation, battery/charger/haptic qualification and source-time synchronization. The full product goal remains open.
