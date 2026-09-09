# Omi → AURA: from a digital prototype to a pendant worth wearing

Reviewed 2026-09-09. Upstream snapshot: [`BasedHardware/omi@f42089f`](https://github.com/BasedHardware/omi/tree/f42089f53c8010dd971b3702ece05a231c9c0c66). AURA baseline: `03b8d748607dce20222dfb8217982880d191f380`. The `?ref=TIEN` URL parameter is not a firmware branch.

[Cited source file identities](omi-source-snapshot.json) record upstream Git blob hashes so the findings remain tied to the reviewed code as Omi changes.

**A04 implementation update:** the baseline findings below are retained as reviewed. Since that review, AURA has added monitored PDM ingress, a bounded audio FIFO, serialized recorder, real Opus encoding, a recoverable NAND journal/SPI command core, and the shared C/Python revision-3 archive. The integrated DK cross-build and host fault tests pass; no A04 physical recording has been qualified. Verified local import, real Whisper transcription, stable owner/capture ingestion across token rotation and retained portal source metadata also exist. The companion checkpoint passes 95 tests; actual local Next.js/Convex integration used synthetic speech. [Current firmware evidence](../../firmware/a04/README.md), [companion evidence](../../companion/VERIFICATION.md) and [the A04 requirements matrix](../a04/requirements.md) distinguish that progress from outstanding device, mobile, electrical and mechanical work.

**Decision:** keep AURA's deliberate capture, physical microphone disconnect, recoverable local audio and owner-approved AI context. Adopt Omi's attention to reconnection, compression, mobile recovery and measured hardware tests. First validate wearing and recording on an off-the-shelf development board; revise AURA's component placement before ordering assembled custom boards. Omi's consumer electronics are substantially more complex to fabricate than AURA's module-based design.

This is a bounded source review, not an exhaustive security audit or a claim that either device was tested on a body. The clone was inspected without running its applications or firmware. Hardware, battery, radio and phone-background behavior require physical tests. No board order has been placed.

## What the codebase actually contains

| Layer | Omi source | Purpose and implication for AURA |
|---|---|---|
| Product contracts | [`PRODUCT.md`](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/PRODUCT.md), `product/invariants/` | Capture → understand → remember → retrieve → act; recovery and consistent state are product requirements. Some memory policies are proposals, not proof of shipped behavior. |
| Consumer firmware | [`omi/firmware/omi/`](https://github.com/BasedHardware/omi/tree/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/omi) | Zephyr/Nordic SDK, nRF5340, audio encoding, Bluetooth, SD storage and device controls. Cannot be flashed onto AURA's nRF52840. |
| Development firmware | [`omi/firmware/devkit/`](https://github.com/BasedHardware/omi/tree/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/devkit) | Separate XIAO nRF52840 Sense configurations. Relevant to a learning prototype and codec experiments; pins, storage and charging differ from AURA. |
| Electronics and mechanics | [`omi/hardware/`](https://github.com/BasedHardware/omi/tree/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/hardware) | Several generations coexist. A schematic, enclosure or firmware from one generation is not automatically compatible with another. |
| Phone | [`app/`](https://github.com/BasedHardware/omi/tree/f42089f53c8010dd971b3702ece05a231c9c0c66/app) | Flutter iOS/Android capture, sync, pending uploads and result presentation. This is the largest missing everyday-use layer in AURA. |
| Services | [`backend/`](https://github.com/BasedHardware/omi/tree/f42089f53c8010dd971b3702ece05a231c9c0c66/backend) | FastAPI with Firebase/Firestore and other services. Adopt useful contracts without importing a second backend beside AURA's Convex. Backend architecture was mapped; every endpoint was not audited. |
| Device SDK and AI access | [`sdks/python/`](https://github.com/BasedHardware/omi/tree/f42089f53c8010dd971b3702ece05a231c9c0c66/sdks/python), [`mcp/`](https://github.com/BasedHardware/omi/tree/f42089f53c8010dd971b3702ece05a231c9c0c66/mcp) | Helpful protocol and integration references. AURA already offers local Whisper, reviewed Context Packs and read-only MCP; another AI integration marketplace is not needed for the first unit. |

Detailed companion reviews: [hardware and assembly](omi-hardware-review.md), [product and mobile recovery](omi-product-review.md).

## Design principles to retain

1. **Trust is a feature.** The user must know whether a thought was captured, saved locally, transferred, transcribed or uploaded. A single ambiguous “connected” status is insufficient.
2. **Wearable hardware should ask for little attention.** A tactile capture control, one recognizable state indicator, physical privacy and a comfortable, snag-conscious attachment matter more than another sensor.
3. **The record is authoritative; the summary is editable.** Preserve audio/transcript provenance, show uncertainty, and make AI memory a user-approved view. A model summary cannot prove what was said.
4. **Recover before adding features.** App suspension, a dead phone, a full journal and a failed upload are normal states to design for.
5. **Measure the complete object.** Antenna behavior changes near a body and metal chain; microphone quality changes inside a case. A successful build and a clean copper check do not measure either.

Omi's documented intent is evidence of design direction, not evidence that every implementation satisfies it. See the product review for the proposed/locked memory-policy discrepancy.

## Firmware findings worth learning from

### Compression is useful, but it needs a measured port

The inspected dev-kit configuration uses 160 samples per frame (10 ms at 16 kHz), a 32,000 bit/s Opus target, VBR and complexity 3. Consumer configuration uses 320 samples (20 ms), the same bitrate target and a different codec ID. [Dev-kit configuration](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/devkit/src/config.h#L24-L43), [consumer configuration](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/omi/src/lib/core/config.h#L24-L43).

The reviewed A03 baseline stores 256,000 bit/s PCM; the later A04 implementation above adds real Opus encoding. The target bitrate ratio is 8:1 before framing, variable bitrate, metadata and bad blocks. This is not an eightfold battery-life claim. The dev-kit encoder also reserves a 32,000-byte thread stack and a codec state buffer; CPU deadlines, RAM, power and speech quality must be measured on AURA alongside NAND and Bluetooth. [Encoder implementation](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/devkit/src/codec.c#L51-L117).

Proposed AURA protocol v2: codec/version metadata, frame sequence and timestamps, local commit before release, compressed-file CRC, explicit durable host acknowledgement, bookmark offsets, and negotiated transfer capability. Retain v1 PCM reading for existing recordings. This is a specification direction; no untested codec was inserted into the A03 release.

### P1: live transmit failures can lose dequeued audio

In the consumer `pusher`, a frame leaves the queue before connection/subscription decisions. With a connected but unsubscribed peer, it is neither sent nor stored. When subscribed, the return value of `push_to_gatt()` is ignored; that function returns false after three failed send attempts. Offline storage is only selected by the `!conn` branch. These are static code paths, not a measured loss rate. [Transmit retry](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/omi/src/lib/core/transport.c#L1066-L1130), [routing decision](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/omi/src/lib/core/transport.c#L1214-L1254).

Improvement: retain an identified frame in durable storage until the receiving application commits it, replay gaps after reconnection, and expose an explicit overflow/failure state. Test connection-before-subscription, reconnect during a sentence, notification exhaustion and phone process termination. AURA already records locally before its later sync; keep that advantage.

### P1: radio transmit completion is weaker than durable app acknowledgement

Consumer storage counts bytes in `storage_data_tx_done()` and uses that count to advance the persisted SD read pointer. The callback is attached to a GATT notification. Its comments describe the phone as having confirmed receipt, but Zephyr's callback indicates transmission, not completion of an application file/database write. A phone crash in that gap could leave neither a durable phone copy nor a retained device copy. [Storage callback](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/omi/src/lib/core/storage.c#L245-L255), [pointer advancement](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/omi/src/lib/core/storage.c#L384-L435), [Zephyr GATT semantics](https://docs.zephyrproject.org/latest/services/connectivity/bluetooth/api/gatt.html).

An explicit advance command also exists in this source; it does not remove the automatic callback-based advancement path described above. This finding concerns the strength of the acknowledgement contract, not an assertion that every transfer fails.

Improvement: acknowledge `{device, stream, committed sequence, checksum}` from the app after durable local publication; make acknowledgements monotonic and idempotent. Test killing the receiver after notification but before its file commit. AURA's explicit CRC-verified deletion is slower, but should not be replaced with radio-completion deletion.

### P2: full-storage behavior must be an explicit product choice

Omi's consumer ring advances its read pointer and increments `dropped_packets` when writes overtake unread data. This is an intentional rolling-buffer policy in the inspected code, not proof of silent loss in every UI. [Ring overwrite handling](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/omi/src/sd_card.c#L513-L532).

For AURA's deliberate notes, preserve an unsynced thought and clearly stop when full. Later reclaim acknowledged/deleted segments incrementally; the current all-notes-delete plus full-device maintenance flow is too cumbersome for daily use. Power-loss tests must accompany garbage collection.

### Reuse selectively

The [root MIT license](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/LICENSE) permits reuse with its notice; bundled third-party libraries have their own notices. No Omi implementation was copied in this change. Link the pinned sources and preserve applicable notices if a later port includes code.

Build documentation also needs generation-specific interpretation: the generic [compile guide](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/docs/doc/developer/firmware/Compile_firmware.mdx) lists SDK 2.7.0 for the dev kit and 2.9.0 for consumer, but then presents a XIAO target in its shared build step. The consumer [application README](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/omi/README.md#L5-L13) explicitly selects `omi/nrf5340/cpuapp`. Keep separate tested recipes rather than applying the generic target to both boards.

The Python SDK pins Bleak 0.22.3, whereas AURA pins Bleak 3.0.2; it should not be installed blindly into the same environment. Its simple decoder strips the three-byte header and catches decoding errors; use the sequence/fragment information and expose gaps before relying on it for archival capture. [Dependencies](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/sdks/python/pyproject.toml), [decoder](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/sdks/python/omi/decoder.py).

## Changes implemented in AURA from this review

- Repeat sync verifies the existing WAV's full PCM checksum, size, format and matching capture metadata before reusing it. A metadata flag alone cannot skip transfer. A missing WAV is downloaded again; corrupt or conflicting files are preserved and rejected.
- Recovery after interruption between WAV publication and metadata publication validates the WAV against the current device record and repairs its receipt without re-reading Bluetooth audio.
- WAV data is flushed before publication. Notes and receipts use flushed temporary files and atomic replacement, preserving a previous file if replacement fails. JSON is authoritative; Markdown is a derived view. The two files are not an atomic multi-file transaction.
- Bluetooth transfer and note processing are separated. The radio session closes before Whisper, Ollama or an opted-in upload. A processing failure does not prevent later verified notes being processed, and recovery status stays beside the WAV.

See [companion verification](../../companion/VERIFICATION.md) for executed tests. The physical firmware, PCB, case and existing release archive remain unchanged. AURA still needs a mobile client, authenticated device identity, automatic reconnect coordination, durable upload outbox, faster measured transfer, exported bookmarks and a qualified charger/dock.

## A practical route to your first wearable

The first success criterion is **you can wear it, deliberately record a thought, find that thought later and recover from a phone disconnect**.

| Stage | Work and artifact | Exit evidence |
|---|---|---|
| 1. Audio/comfort learning unit | Use the exact original XIAO nRF52840 **Sense** supported by Omi's dev-kit instructions, an appropriately specified protected cell, insulating case and breakaway attachment. Keep its firmware and charger wiring matched to that board. | Correct device firmware; measured supply/charge current; unobstructed mic and antenna; no exposed conductors, cell compression or sharp edges. |
| 2. Daily interaction trial | Use the matching Omi phone path to learn real phone/background behavior. Keep this separate from AURA's incompatible v1 GATT protocol. A local WAV can already enter AURA via `aura transcribe PATH`. | Recorded spoken checklist indoors, walking and under clothing; captures recover after reconnect; local note can be found and manually exported to a chosen AI. Do not assume unimplemented automatic Omi→AURA sync. |
| 3. A04 custom engineering | Revise A03 placement to resolve actual courtyard collisions; choose exact purchasable battery/contact/motor parts; complete a protected charging dock. Retain the RF-transparent housing and module antenna keepout. | Assembly-house approval for exact process/BOM/rotations; updated schematic/PCB/ERC/DRC and manufacturing exports; measured-component enclosure stack-up. |
| 4. Bench bring-up | Assemble a small engineering batch, initially with reviewed current-limited power. Verify rails, polarity, SWD, microphones, NAND recovery and privacy disconnect. Qualify battery, NTC fault handling and haptics before enabling their release flags. | Recorded measurements against component limits and the existing thermal/firmware bring-up plan; known-good test recording and recovered power-cut recording. |
| 5. Enclosed wearable trial | Verify the closed case, strain relief, attachment, off-body charging and body/chain RF behavior. Record actual mass, thickness and runtime. | Successful fit/acoustic/RF/thermal tests; demonstrated charging and fault behavior; short supervised wear followed by a longer documented trial. No claimed ingress rating without a test. |

The original Sense is a 21 × 17.8 mm development board with a microphone and onboard charger, according to [Seeed's hardware documentation](https://wiki.seeedstudio.com/XIAO_BLE/). This does not establish battery compatibility or fit in AURA's existing STLs. **Do not flash the AURA A03 binary onto it, or put it into the A03 case without a separate measured layout.** [Omi's dev-kit assembly guide](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/docs/doc/assembly/Build_the_device.mdx) and [buying guide](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/docs/doc/assembly/Buying_Guide.mdx) are useful references, not qualification of arbitrary batteries.

For the custom device, A03 is a reviewed **bare-board prototype** package with 78 unresolved assembly courtyard findings. Do not describe it as an assembly-approved, battery-qualified or ready-to-wear product. [Every collision classified](aura-a03-courtyard-classification.json), [native package](../../hardware/native/README.md), [thermal review](../thermal-review.md), [firmware bring-up](../../firmware/README.md), [print guide](../../enclosure/PRINTING.md).

The MK2 microphone/U7 regulator pair is a concrete placement blocker: the nominal fabrication drawing envelopes have only 0.020 mm clearance, and the allowed maximum body lengths can overlap by 0.005 mm before placement tolerance. The hardware review provides the manufacturer drawings and calculation. Clearing copper checks does not resolve that tolerance stack.

## What would make AURA better for this use

Keep the compact jewellery direction, but freeze further thinning until the real cell, antenna, button travel and case tolerances are measured. Prioritize tactile recording, unambiguous saved status, trustworthy offline recovery, one phone recovery owner and source-backed context. Make an eight-hour wear trial with a defined amount of actual recording an engineering target, then measure it; do not publish “all-day” from cell capacity alone.

The next custom-board milestone is a released **A04 placement/BOM/dock review with assembly evidence**. The next software milestone is **recoverable mobile capture and sync**. These decisions keep the path to a device you personally wear concrete and testable.
