# AURA A04: experimental Opus capture core

This directory contains an actual libopus encoder, a bounded PCM-to-packet capture wrapper, host failure/round-trip tests, and an isolated Zephyr Cortex-M4 build. It is **not the complete A04 wearable firmware**. It does not alter the published A03 firmware or claim working microphones, storage, BLE, signed updates or measured battery life.

## Implemented behavior

- Arbitrary mono PCM16 chunks are accumulated into 16 kHz frames. The selected profile is 32 kbps constrained VBR, complexity 3, wideband, `OPUS_APPLICATION_RESTRICTED_LOWDELAY`; 20 ms is the primary profile and 10 ms is also tested. DTX and in-band FEC are disabled. This chooses the CELT low-delay mode, so it must be compared against the speech-optimized Opus modes on actual voices before the product profile is locked.
- The application queries `opus_encoder_get_size(1)` and initializes caller-provided, correctly aligned memory. It never hard-codes Omi's older, modified encoder-state sizes. The current fixed-point host build reports **15,268 bytes**. A 32 KiB upper-bound reservation is checked before initialization.
- A failed sink commit retains the exact encoded packet for retry. New input waits while that packet is pending. `*consumed` tells the producer exactly which PCM samples were copied before a failure; resubmit only the unconsumed remainder. The sink must make retries idempotent by stream identity, sequence and payload hash.
- Finish flushes the encoder lookahead and partial final frame. The seal records source length, encoded length, pre-skip and end-trim. Repeated finish after a commit failure does not re-encode that packet. No further source audio is accepted after closing begins.
- Allocation and scratch storage are bounded in the embedded application. The upstream fixed-point implementation uses stack `alloca`; the probe provides a separate 48 KiB codec thread stack, initializes stack memory and enables the MPU guard and stack-space query. Runtime stack headroom is still unmeasured.

The capture object and sink have **one serialized owner**. They are not ISR-safe or thread-safe. A PDM producer must use a separate bounded queue and apply a defined overflow policy. Pending audio here survives a retry in RAM; only a successful *real durable sink* can establish flash persistence. Neither test sink establishes that guarantee: the host sink stores in memory, and the synthetic embedded probe deliberately discards packets. Persist the returned seal transactionally before treating a recording as closed.

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
```

The setup uses Python 3.12, Zephyr v4.2.0, SDK 0.17.2, CMake 3.31.6, Ninja 1.11.1.4 and Zig 0.14.1 from the existing repository setup. Host round trips additionally require `ffmpeg` on PATH. Build products stay under `.tools/a04-opus/`; the scripts do not flash, copy artifacts into `firmware/release/`, or change A03 board files. First builds compile the full unmodified source and take several minutes.

The ARM target is `nrf52840dk/nrf52840`. It checks the MCU ABI and linker budget while the A04 hardware contract is being finalized; **do not flash this DK probe onto AURA**. On a matching Nordic DK, a future manual run will print codec version, state size, worst encode time, late frames and stack free space to the console. No such run has been performed for the checked-in evidence.

## Verification and inspectable audio

The host test covers state size/alignment, unsupported profiles, missing sink, empty capture, arbitrary chunk boundaries, repeated sink failure, byte-identical retry, failure while flushing a final partial frame, exact duration and rejection of input after closing. The speech fixture is encoded using the real fixed-point encoder, decoded by the linked libopus decoder, then independently decoded by FFmpeg through standards-compatible Ogg Opus files.

| Profile | Packets | Payload | Payload bitrate on this fixture | Exact decoded samples | Source-to-host waveform SNR |
|---|---:|---:|---:|---:|---:|
| 10 ms | 756 | 27,365 bytes | 28.98 kbps | 120,847 | 11.981 dB |
| 20 ms | 378 | 26,998 bytes | 28.60 kbps | 120,847 | 11.918 dB |

Both use 40 samples of pre-skip and 73 samples of final trim at 16 kHz for this 7.553-second synthetic speech input. Constrained VBR is not a constant packet-size guarantee. Waveform SNR is only a regression check for this exact fixture; it does not establish perceptual quality or transcription accuracy. FFmpeg outputs have the same exact duration. Full metrics, hashes and exclusions are in [host-roundtrip.json](verification/host-roundtrip.json).

The actual nRF52840 cross-build uses **170,520 bytes of flash (16.26%)** and **90,304 bytes of RAM (34.45%)**. This includes a 32,768-byte encoder arena, a 49,216-byte guarded thread-stack object (48 KiB usable reservation plus alignment/guard overhead), a 1,992-byte capture context and a 640-byte input buffer. These are linked resource reservations for the isolated synthetic probe, not the complete product budget. [arm-resources.json](verification/arm-resources.json) records ELF symbols, source/config hashes, artifact identities and compiler stack reports; [arm-build.txt](verification/arm-build.txt) retains the successful linker output. No Cortex-M4 runtime timings or stack high-water measurements are claimed. The existing A03 release hash/source checker also passes unchanged.

Listen or inspect: [input WAV](fixtures/source-speech-16k.wav), [20 ms Opus](fixtures/speech-20ms.opus), [20 ms independent decode](fixtures/speech-20ms-ffmpeg.wav), [10 ms Opus](fixtures/speech-10ms.opus). Host-generated `.aoc` files retain individual packets for debugging. Ogg files use 48 kHz granule units and encode both pre-skip and exact final length.

The `.aoc` container is **AOC1, a test fixture format only**, not AURA protocol v2. Integers are little-endian: header `<4sHHIQQIHH>` contains magic, version, frame milliseconds, rate, source samples, encoded samples, packet count, pre-skip and end-trim; each packet uses `<IQHH>` for sequence, encoded sample offset, sample count and payload bytes, followed by that payload. It has no journal CRC, identity or durable receipt mechanism. Production framing remains covered by the separate [software contract](../../docs/a04/software-contract.md).

## Evidence required before wearable integration

1. Final A04 pin map and Zephyr board definition, actual PDM mono/channel selection, clocking, gain, DC/clipping behavior and microphone power gating.
2. Device measurements of encode latency and stack high-water with representative voice, long recordings, flash writes and concurrent BLE; tune complexity/profile only from those results.
3. A durable append-only packet/seal sink with CRC, identity, power-loss recovery, media-full handling and persistent host ACK reclamation. Test storage stalls against the PCM queue budget.
4. Actual BLE fragmentation, flow control, disconnect/reconnect and mobile-background recovery against the receiving implementation; the codec wrapper does not supply transport.
5. Signed boot/OTA, authenticated ownership, privacy controls, indication/haptics, bookmarks and orderly battery/charger shutdown integrated with the hardware contract.
6. End-to-end transcription, memory/context provenance, search/tasks, live and offline flows, controlled continuous capture and phone/earbud interaction. These remain part of AURA's full feature objective; this encoder experiment does not replace them.

## Sources and license

The [official Opus downloads page](https://opus-codec.org/downloads/) supplies the pinned 1.6.1 checksum; the [encoder API reference](https://opus-codec.org/docs/opus_api-1.5/group__opus__encoder.html) documents supported frame lengths, state sizing, lookahead and low-delay behavior. The actual selected controls were also checked against the 1.6.1 headers. [Third-party notices](THIRD_PARTY_NOTICES.md) and [the full upstream license](licenses/Opus-COPYING.txt) accompany this integration.

The Omi comparison used [`BasedHardware/omi` at f42089f53c8010dd971b3702ece05a231c9c0c66](https://github.com/BasedHardware/omi/tree/f42089f53c8010dd971b3702ece05a231c9c0c66). Its 10 ms, 32 kbps, complexity-3 fixed-point approach informed the profile experiment. AURA uses an unmodified current upstream dependency and queried state sizes; no Omi codec source was copied.
