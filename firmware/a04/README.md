# AURA A04: microphone ingress, Opus capture and recoverable storage

This directory contains a monitored PDM driver, bounded reader FIFO, serialized recorder, actual libopus encoder, revision-3 archive writer, recoverable NAND journal and W25N01GV command core/Zephyr SPI adapter. A serialized storage owner combines authenticated release commands, durable identity reservations and control snapshots for host-tested capture reclamation. A matching Python reader, durable receiver and release outbox complete the tested source-to-release path. Host failure/round-trip tests and a Cortex-M4 integration build exercise these layers. It is **not the complete A04 wearable firmware**. It does not alter the published A03 firmware or establish physical microphones, NAND storage, BLE, signed updates or measured battery life.

The separate [first spoken-note bench](bench/README.md) now connects these layers to the nRF52840 DK's actual PDM/SPI/GPIO drivers and a bounded local UART host. It has explicit microphone permission, recording, cold-open recovery and verified archive export. The [wiring review](bench/WIRING.md) names microphone fixtures matching A04 and a W25N01GV fixture; the [bench ELF report](bench/verification/arm-resources.json) checks the separate target and pins. Its 31 UART-client tests and five C orchestration groups cover the new integration. It has been cross-built, **not flashed or physically tested**. The original ARM probe below remains a different synthetic integration target.

## Implemented behavior

The separate [authenticated radio DK application](radio/README.md) now connects
the same physical-driver/storage owner to the actual transfer command engine.
It includes a bounded pairing window, L4 enforcement, per-connection ASC1 owner
proof, immutable GATT responses and immediate revocation. This is development
source with host-tested boundaries, not an executed physical radio link or
consumer enrollment. The wired bench and the synthetic ARM probe remain
separate targets; their existing resource reports do not measure this radio image.

- The [storage owner](STORAGE.md) durably reserves capture IDs, verifies exact finalized source and [RLS1 authentication](RELEASE-AUTH.md), then commits original release extents through [control snapshots](CONTROL-LEDGER.md) before invoking a privileged erase. It preserves unacknowledged recordings and supports catalog reuse in the host model. The W25N adapter separately supports restricted control-block rotation; a production populated-audio erase callback and secure owner enrollment remain unimplemented. An interrupted authority write can require recovery and block further operations. Authentication success alone never permits deletion.
- The [microphone adapter](AUDIO.md) separates its higher-priority PDM reader from the encoder/storage owner with a bounded FIFO. The local Zephyr/nrfx driver exposes sticky faults and DMA ownership; overflow, missing blocks, privacy cancellation or uncertain STOP completion cannot masquerade as a clean recording. Startup, publication and cutoff ordering have deterministic host tests. Real interrupt latency and microphone continuity remain unmeasured.
- The [recorder](RECORDER.md) binds each block to an epoch, sequence and exact source offset. A clean stop checks the producer's final watermark before flushing and sealing; interrupted captures retain their verified complete-packet prefix. It reports separate source and storage-close errors and prevents retrying PCM already consumed on a failed call.
- Arbitrary mono PCM16 chunks are accumulated into 16 kHz frames. The selected profile is 32 kbps constrained VBR, complexity 3, wideband, `OPUS_APPLICATION_RESTRICTED_LOWDELAY`; 20 ms is the primary profile and 10 ms is also tested. DTX and in-band FEC are disabled. This chooses the CELT low-delay mode, so it must be compared against the speech-optimized Opus modes on actual voices before the product profile is locked.
- The application queries `opus_encoder_get_size(1)` and initializes caller-provided, correctly aligned memory. It never hard-codes Omi's older, modified encoder-state sizes. The current fixed-point host build reports **15,268 bytes**. A 32 KiB upper-bound reservation is checked before initialization.
- A failed sink commit retains the exact encoded packet for retry. New input waits while that packet is pending. `*consumed` tells the producer exactly which PCM samples were copied before a failure; resubmit only the unconsumed remainder. The sink must make retries idempotent by stream identity, sequence and payload hash.
- Finish flushes the encoder lookahead and partial final frame. The seal records source length, encoded length, pre-skip and end-trim. Repeated finish after a commit failure does not re-encode that packet. No further source audio is accepted after closing begins.
- The archive layer binds immutable device/capture metadata, packet CRCs, SHA256 chain, source bookmarks and the exact finalized/interrupted terminal seal. It retains exact bytes and file offsets across uncertain sink writes. A real host file sink flushes each committed record; a Python SQLite receiver batches import into one transaction and returns its receipt only after commit. [ARCHIVE.md](ARCHIVE.md) defines the complete byte contract and integration API.
- The [packed NAND journal](NAND-JOURNAL.md) uses separate staged initializers, full page readback and replay-derived committed receipts, metadata-only mount, strict gap/checkpoint recovery, and lazy full verification before export. Version-2 allocation headers/checkpoints bind storage incarnation and generation to each part. Its host model covers power-cut program/erase cases. A [Zephyr SPI adapter](W25N-ADAPTER.md) accepts the eventual reviewed board configuration without choosing GPIOs. Media-full stops recording; connecting the authorized reclamation path to physical audio storage remains a product gap.
- Allocation and scratch storage are bounded in the embedded application. The upstream fixed-point implementation uses stack `alloca`; the probe provides a separate 48 KiB codec thread stack, initializes stack memory and enables the MPU guard and stack-space query. Runtime stack headroom is still unmeasured.

The capture object and sink have **one serialized owner**. They are not ISR-safe or thread-safe. The audio adapter provides a separate bounded queue and an explicit overflow policy; the embedding product still needs its real task scheduler. Pending codec audio survives a retry in RAM. The codec-only test sink stores in memory; the archive test sink performs host file writes and `_commit`/`fsync`; the synthetic embedded probe uses a small volatile RAM NAND and discards only its verified export. It retains the physical SPI adapter without initializing a flash device. Host file tests do not establish NAND persistence on a physical device. Persist the returned seal before treating a recording as closed.

## Reproduce on the existing Windows toolchain

From the repository root:

```powershell
# Once, if the repository's pinned Zephyr tools are not installed:
./firmware/scripts/setup.ps1

# Installs/verifies the local Opus dependency, then builds and tests:
./firmware/a04/scripts/build.ps1 -Mode all

# Independent subsets:
./firmware/a04/scripts/build.ps1 -Mode host
./firmware/a04/scripts/build.ps1 -Mode arm

# Once when migrating an older generated codec-only build:
./firmware/a04/scripts/build.ps1 -Mode arm -Pristine
```

The setup uses Python 3.12, Zephyr v4.2.0, SDK 0.17.2, CMake 3.31.6, Ninja 1.11.1.4 and Zig 0.14.1 from the existing repository setup. Host round trips additionally require `ffmpeg` on PATH. Build products stay under `.tools/a04-opus/`; the scripts do not flash, copy artifacts into `firmware/release/`, or change A03 board files. First builds compile the full unmodified source and take several minutes.

The ARM target is `nrf52840dk/nrf52840`. It checks the MCU ABI and linker budget while the A04 hardware contract is being finalized; **do not flash this DK probe onto AURA**. On a matching Nordic DK, a future manual run will print codec version, state size, worst encode time, late frames and stack free space to the console. No such run has been performed for the checked-in evidence.

## Verification and inspectable audio

The integrated verification covers **25 SPI command/integration groups, 19 journal groups, 13 storage-owner groups (745 cases), 10 recorder groups, 10 audio-adapter groups, 20 monitored-driver groups and 33 Python archive/receiver tests**. Six real-Opus journal recovery cases and five recorder cases pass export, SQLite restart/replay and independent FFmpeg decode. The additional [storage round trip](verification/storage-roundtrip.json) sends real C-encoded audio through a committed Python receiver and persisted release outbox back to C, proving exact authorization, cold recovery, reclaimed-block reuse and byte-identical retained audio. The complete [companion suite](../../companion/verification/release.json) passes 131 tests, including 36 release tests. The [adapter report](verification/audio-host.json) and [driver report](drivers/tests/verification.json) bind their tested sources. These are host tests with simulated boundaries; none establishes physical flash or microphone operation.

The host test covers state size/alignment, unsupported profiles, missing sink, empty capture, arbitrary chunk boundaries, repeated sink failure, byte-identical retry, failure while flushing a final partial frame, exact duration and rejection of input after closing. The speech fixture is encoded using the real fixed-point encoder, decoded by the linked libopus decoder, then independently decoded by FFmpeg through standards-compatible Ogg Opus files.

| Profile | Packets | Payload | Payload bitrate on this fixture | Exact decoded samples | Source-to-host waveform SNR |
|---|---:|---:|---:|---:|---:|
| 10 ms | 756 | 27,365 bytes | 28.98 kbps | 120,847 | 11.981 dB |
| 20 ms | 378 | 26,998 bytes | 28.60 kbps | 120,847 | 11.918 dB |

Both use 40 samples of pre-skip and 73 samples of final trim at 16 kHz for this 7.553-second synthetic speech input. Constrained VBR is not a constant packet-size guarantee. Waveform SNR is only a regression check for this exact fixture; it does not establish perceptual quality or transcription accuracy. FFmpeg outputs have the same exact duration. Full metrics, hashes and exclusions are in [host-roundtrip.json](verification/host-roundtrip.json).

The current synthetic nRF52840 probe links the new transfer owner and all nine
of its APIs: **227,488 bytes of flash (21.70%)** and **224,768 bytes of RAM
(85.74%)**, leaving 37,376 bytes unallocated in this specific configuration.
The [resource report](verification/arm-resources.json) binds the actual ARM ELF
and [unchanged build inputs](verification/arm-inputs.json). The owner occupies
**4,440 bytes** on ARM, including its cursor and response buffer, and remains
uninitialized in this probe. This establishes compilation and allocation, not
transfer execution or production Bluetooth headroom. The probe also contains
synthetic RAM NAND and a maximum control snapshot reservation.

The separate [wired bench report](bench/verification/arm-resources.json) covers
actual peripheral-driver code and cursor-based UART EXPORT; it does not include
the new command owner. Neither report measures physical runtime timing or stack
high-water, and neither is a complete wearable firmware budget. Production
Bluetooth, enrollment, audio-release capability, signed updates and real
workload measurements remain outstanding.

The [bounded export cursor](JOURNAL-CURSOR.md) adds exact-record resume, an owned
page buffer and at most one NAND read per step. It independently verifies source
before streaming and again before completion. Its host tests check source
mutation, interrupted tails, chunk sizes, exact resume boundaries and volatile
cancellation. The wired bench uses it for EXPORT; its UART protocol still has
no resumable command or concurrent command preemption.

The portable [transfer command owner](include/aura_transfer.h) adds HELLO, LIST,
SELECT, READ, FINISH and CANCEL above that cursor. Its
[exact wire contract](../../docs/a04/transfer-wire-v1.md) separates immutable
response delivery from durable phone storage, binds exports to owned allocation
identities and rejects stale connection/source/delivery callbacks. Its
[12 host test groups](verification/transfer-host.json) exercise real journal and
cursor code with modeled NAND, unchanged Opus packets and generation-derived
identities. Tests generate [exact replies and fragments](verification/transfer-wire-golden.tsv)
for the matching Android codec. Reproduce with
`python firmware/a04/scripts/verify_transfer.py` after configuring the host build;
the normal `scripts/build.ps1 -Mode host` loop includes it. This new owner is
linked as a resource reservation in the synthetic ARM probe and is now integrated
into the separate radio DK application's owner loop. The wired bench still uses
its UART cursor. Durable phone download and the Android GATT client exist with
virtual-peripheral tests; matching ASC1 client integration, consumer enrollment
and a physical hardware-to-phone recovery trial remain outstanding.

Listen or inspect: [input WAV](fixtures/source-speech-16k.wav), [20 ms Opus](fixtures/speech-20ms.opus), [20 ms independent decode](fixtures/speech-20ms-ffmpeg.wav), [10 ms Opus](fixtures/speech-10ms.opus). Host-generated `.aoc` files retain individual packets for debugging. Ogg files use 48 kHz granule units and encode both pre-skip and exact final length.

The `.aoc` container is **AOC1, a codec-debug format only**. Integers are little-endian: header `<4sHHIQQIHH>` contains magic, version, frame milliseconds, rate, source samples, encoded samples, packet count, pre-skip and end-trim; each packet uses `<IQHH>` for sequence, encoded sample offset, sample count and payload bytes, followed by that payload. It has no journal CRC, identity or durable receipt mechanism. It is rejected by the real archive reader.

The real `.aura` fixtures use [experimental wire revision 3](ARCHIVE.md): [10 ms finalized](fixtures/capture-10ms.aura), [20 ms finalized](fixtures/capture-20ms.aura), [20 ms interrupted](fixtures/capture-20ms-interrupted.aura) and [20 ms unsealed prefix](fixtures/capture-20ms-open.aura). Their adjacent `.receipt` files are independently serialized by C. Python verifies the exact C terminal receipts, imports/replays after restart, and reconstructs Opus for independent FFmpeg decode. Finalized fixtures preserve exactly 120847 source samples; interrupted fixtures retain 120600 samples with original duration unknown. A tail bookmark at sample 120640 remains recorded but unavailable in the interrupted audio. [archive-roundtrip.json](verification/archive-roundtrip.json) records exact file/terminal/prefix hashes and results. This is an explicit version change; there is no revision-2 conversion or BLE wire compatibility claim.

## Evidence required before wearable integration

The underlying primitives add **13 authentication groups and four independent Python comparisons**, plus **12 control-ledger groups covering 712 fault/rotation cases**. [Authentication evidence](verification/release-auth.json) covers standard HMAC vectors, every message-bit mutation, canonical fields, exact receipts and replay checks. [Control evidence](verification/control-ledger.json) covers power cuts, stale contexts, bounded output, generation conflicts and preserved unrelated source, with independent wire/hash decoding. The storage-owner tests combine these layers, but secure enrollment and physical audio-release integration remain outstanding.

1. Final A04 pin map and Zephyr board definition, actual PDM mono/channel selection, clocking, gain, DC/clipping behavior and microphone power gating.
2. Device measurements of encode latency and stack high-water with representative voice, long recordings, flash writes and concurrent BLE; tune complexity/profile only from those results.
3. Physically validate the implemented journal/SPI adapter, power-loss reconstruction and media-full behavior; integrate the separate authorized audio-erase driver capability, trusted enrollment and recovery of ambiguous control/unassociated blocks. The current 128-live-capture bound and short-block tail waste are quantified in NAND-JOURNAL.md. Test storage stalls against the PCM queue budget and measure control-block wear.
4. Actual BLE fragmentation, flow control, disconnect/reconnect and mobile-background recovery against the receiving implementation; the codec wrapper does not supply transport.
5. Signed boot/OTA, authenticated ownership, privacy controls, indication/haptics, bookmarks and orderly battery/charger shutdown integrated with the hardware contract.
6. End-to-end transcription, memory/context provenance, search/tasks, live and offline flows, controlled continuous capture and phone/earbud interaction. These remain part of AURA's full feature objective; this encoder experiment does not replace them.

## Sources and license

The [official Opus downloads page](https://opus-codec.org/downloads/) supplies the pinned 1.6.1 checksum; the [encoder API reference](https://opus-codec.org/docs/opus_api-1.6/group__opus__encoder.html) documents supported frame lengths, state sizing, lookahead and low-delay behavior. The actual selected controls were also checked against the 1.6.1 headers. [Third-party notices](THIRD_PARTY_NOTICES.md) and [the full upstream license](licenses/Opus-COPYING.txt) accompany this integration.

The Omi comparison used [`BasedHardware/omi` at f42089f53c8010dd971b3702ece05a231c9c0c66](https://github.com/BasedHardware/omi/tree/f42089f53c8010dd971b3702ece05a231c9c0c66). Its 10 ms, 32 kbps, complexity-3 fixed-point approach informed the profile experiment. AURA uses an unmodified current upstream dependency and queried state sizes; no Omi codec source was copied.
