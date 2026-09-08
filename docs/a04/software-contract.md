# AURA A04 software and hardware contract

Status: **active engineering specification with an experimental host receiver and real Opus codec probe**. Updated 2026-09-09. The current A03 firmware and its published binaries are unchanged. This document does not establish a working A04 device, a deployed mobile app, qualified battery behavior, or launch readiness.

The target remains a premium circular pendant that reliably captures, preserves, understands, retrieves and uses the context its owner chooses to record. Offline use, optional continuous sessions, real-time assistance, memory, tasks, speech, and broad AI interoperability remain in scope. They are not removed because the initial source is incomplete. “Best in the category” needs measured comparative evidence; it cannot be established by a feature list or source review.

## Evidence and implementation boundary

AURA baseline inspected: `e9e968c425c558565dc555ccd9f39d2e4c6c0769`. Omi source inspected: [`f42089f53c8010dd971b3702ece05a231c9c0c66`](https://github.com/BasedHardware/omi/tree/f42089f53c8010dd971b3702ece05a231c9c0c66). The prior [firmware/hardware review](../research/omi-review.md) and [product review](../research/omi-product-review.md) contain the specific upstream code paths and known limitations.

Three terms distinguish evidence throughout this contract:

- **Implemented** means code exists in this repository. It does not imply physical or deployed validation.
- **Host-tested** means an identified local test exercised a bounded software behavior.
- **Required** means work remains and the feature cannot be advertised as shipped.

New implementation: [protocol_v2.py](../../companion/src/aura_companion/protocol_v2.py) is a standalone reference for strict manifests, audio/bookmark packets, stable capture identity, checksums, replay, durable receiving and finalization. [Its tests](../../companion/tests/test_protocol_v2.py) exercise real SQLite transactions and an abruptly exited child process as well as malformed input. It is **not called by the A03 CLI or firmware**. Opus bytes are preserved opaquely; its synthetic test payloads are not claimed to be decodable audio. No upstream implementation was copied into the receiver; existing Omi citations identify design lessons.

Separate codec progress: [firmware/a04](../../firmware/a04/README.md) now builds unmodified libopus 1.6.1 with a bounded capture/retry/tail-flush wrapper. Real 16 kHz mono, 32 kbps, 10/20 ms fixtures pass host and independent FFmpeg decode with exact duration. The isolated nRF52840DK probe cross-builds at 170,520 bytes flash and 90,304 bytes RAM, including conservative state/stack reservations; no physical execution is claimed. The upstream license and a verified download/file manifest are retained. This encoder is not yet connected to PDM, the durable journal, BLE, or the v2 receiver; its AOC1 test container is not the v2 wire format.

Executed verification: **47 companion tests passed** (28 baseline, 19 v2 cases), recorded in [the saved test output](protocol-v2-verification.txt) with the exact command and explicit physical/mobile/cloud exclusions. New cases cover manifest/packet/receipt validation, header and payload corruption, same-sequence conflict, missing frames, future bookmarks, independent device identities, metadata rebinding, quota failure, final-seal mismatch, restart/lost-ACK replay, a process exit inside the real receive transaction, read-only storage and corrupted/deleted persisted packets. The live-corruption cases use a second database connection while the receiver remains open and require both new and replayed ACKs to fail closed. This proves bounded host behavior, not an Opus port or end-to-end A04 functionality.

## Complete feature and evidence backlog

| Product capability | Current evidence | A04 required behavior and owner | Evidence required before launch |
|---|---|---|---|
| Immediate deliberate capture | A03 physical gesture and local PCM journal implemented; host C tests | Pendant captures without a phone; tactile start/stop, unmistakable recording/saved/error indication | Actual button-to-first-usable-audio latency, startup syllable retention, walking and under-clothing recordings |
| Controlled continuous capture | Required | User-enabled session mode with explicit physical start, continuous visible indicator, clear pause/stop, storage limits and consent guidance | Measured long session with no unexplained gaps; privacy switch stops capture independently of app/MCU state |
| Offline capture | A03 append-only journal/recovery implemented; simulated tests | Durable frames before transfer; no overwrite of unacknowledged recordings; recover interrupted captures | Power cuts at every journal state and during erase; audio remains decodable with explicit truncated-tail metadata |
| Real-time transcription and assistance | Required | Phone streams only device-committed frames; live text marked provisional; durable archive later reconciles gaps | Phone termination, BLE backpressure and network loss preserve source; latency and consistency measured on supported phones |
| Opus compression | Real libopus 1.6.1 wrapper host-tested with decodable 10/20 ms fixtures; isolated nRF52840 probe cross-built | 16 kHz mono, 32 kbps initial experiment; compare low-delay and speech-optimized modes against PCM reference before profile freeze | CPU deadline, stack high-water, heap, power, frame error, quality and transcription comparison under concurrent storage/BLE load |
| Multi-microphone audio | A03 PDM stereo input mixed to mono; no assembled test | Two appropriately spaced microphones; calibrated mono mix/selection; retain original capture format metadata | Channel polarity, phase, clipping, wind/clothing noise and speech intelligibility in the actual sealed case |
| Bookmarks | A03 journal stores marks but v1 cannot export; v2 host-tested packet format | Pendant gesture creates a sample-offset event; phone/portal jump to corresponding transcript/audio | Capture + bookmark + reconnect + export + playback round trip on real firmware |
| Device identity | v1 filenames lack authenticated device identity; v2 host-tested independent device/capture keys | Stable private device identity plus persistent random capture identity; owner binding and physical re-pair/reset flow | Two devices, resets, reboots and credential rotations never merge captures; unauthorized identity claims rejected |
| Reliable reconnection | Desktop v1 resume/cache/CRC host-tested | One mobile lifecycle/recovery owner; serial drain; durable inventory and retry state | iOS and Android foreground/background/process-death matrices, permissions off/on, bonds, out-of-range return |
| Transfer retention and ACK | v1 explicit CRC-verified deletion; v2 durable receive reference host-tested | End-to-end application receipt after durable publication, separate from BLE completion; acknowledged/deleted-segment reclaim | Kill receiver before/after commit, lose ACK, replay and verify exactly one source; MCU garbage collection power-cut tests |
| Searchable notes | Next.js/Convex owner-scoped search implemented and previously locally tested | Capture time confidence, editable title, transcript, summary, tags, filters and source playback | Deployed authenticated account flow; source remains accessible through edit/search/archive/delete |
| Transcription and languages | Local Whisper path implemented; no A04 end-to-end test | Local/offline option plus explicit cloud choice; language detection/selection and accessible corrections | Representative accents/languages/noise, measured quality/cost/latency; disclosure when speaker attribution is uncertain |
| Speaker attribution | Required | Phone/backend diarization with user-correctable labels; never infer a person's identity from a voice without an explicit enrollment feature | Overlap, short utterances, new speakers, corrections and source alignment tests |
| Summaries and provenance | Local timestamped segments and method label; upload currently flattens these | Every derived claim/action links to source capture, transcript revision and sample/time span; retain original and corrections | Regeneration/correction invalidates stale context while retaining inspectable lineage |
| Long-term memory | Chosen notes/profile currently supply context | Explicit review/promotion, edit/retract, provenance and supersession; canonical owner-scoped source truth | No unreviewed memory promotion; revoked/deleted/superseded evidence excluded on next retrieval |
| Tasks and reminders | Draft action strings only | Proposed actions with source evidence, accept/edit/dismiss lifecycle; opt-in reminders and integrations | Retry extraction cannot duplicate accepted tasks; no external side effect before a recorded user choice |
| AI chat interoperability | Reviewed Context Packs and read-only MCP implemented; local verification exists | Searchable owner-approved context for ChatGPT, Claude, Gemini, Grok and compatible clients; clipboard/file fallback remains usable | Actual supported-client connection matrix; current consent enforced; no claim every vendor accepts the same deep link/MCP method |
| Voice interaction/playback | Required | Phone/earbud microphone and speaker provide query/response/playback initially; pendant gesture may trigger the paired client | Clearly identify audio route; disconnected earbuds/phone cannot create an apparent pendant playback failure |
| Ecosystem/SDK | Python v1 companion implemented; v2 reference only | Documented versioned device SDK, export formats and import contracts; adapters for integrations without a second source of truth | Contract fixtures across firmware/mobile/desktop; compatibility, migration and permission tests |
| Battery and storage UX | Raw voltage/free bytes available; charging/haptics disabled in release | Calibrated state, low-space/low-battery warnings, last successful save/sync, bounded maintenance and explicit fault handling | Full charge/discharge curves, worn/runtime profile, near-full capture and restart, charger/NTC faults |
| Secure update/recovery | Required; A03 is a single application slot | Signed boot, rollback-capable update, image compatibility, physical recovery and anti-rollback policy | Wrong board/key/image rejected; power cuts throughout update recover; key management documented |
| Privacy and account lifecycle | Hardware disconnect design, encrypted BLE, scoped portal tokens implemented | Hardware privacy proof, authenticated ownership, protected recordings, credential rotation/revocation, account recovery/export/deletion | Lost device/phone, stale cache, revoked token, deletion and restoration tests; no transcript/secret diagnostic leakage |
| Comfort and launch assets | A03 models/video exist; A04 redesign in progress | All PCB, case, firmware, website, video, specs and assembly guides refer to one verified A04 configuration | Render/model/part manifests match released PCB/BOM and physically measured first article; no A03 images labelled A04 |

Speech synthesis, LLM inference, semantic search and task execution belong on the phone/backend. Audio playback belongs on the paired phone/earbuds unless a separately reviewed speaker is added. The A04 hardware contract currently contains no speaker, display, camera, cellular or standalone Wi-Fi feature. None should be implied by a render, voice-over or generic comparison with Omi. Controlled continuous capture and near-real-time transfer remain pendant firmware requirements, not phone-only substitutes.

## Omi engineering practices to adopt

1. **One capture truth and one recovery owner.** Omi's [product principles](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/PRODUCT.md) prioritize reliable capture/sync/retrieval. Its [transfer coordinator](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/app/lib/services/wals/recording_transfer_coordinator.dart) is a useful reference for coalesced recovery. AURA must implement one serial mobile owner, durable inventory and explicit phases: recording → preserved on pendant → preserved on phone → processing → note ready. Connection alone proves none of these.
2. **Contracts plus real failure harnesses.** Preserve bounded regression cases: process exit before/after commit, full storage, dropped notifications, permissions, background restrictions, stale retrieval consent, and interrupted update. Generated checks must actually exercise the shared implementation and run locally/Vercel as applicable; no GitHub Actions.
3. **Compression selected by measurement.** Omi's [dev-kit codec](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/devkit/src/codec.c) reserves a 32,000-byte encoder stack and codec state. Its [configuration](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/firmware/devkit/src/config.h) selects 160-sample, 32 kbps frames. AURA should port the approach with resource accounting; do not copy a static codec-state size without confirming the selected build's `opus_encoder_get_size()`.
4. **Source-backed, revocable memory.** Omi's memory model and access gateway inspire provenance, revisions and fresh policy checks. AURA's canonical record is the owner-scoped capture/transcript and its reviewed derivatives. Search/vector indexes are derived candidates and must be rehydrated against current ownership/consent/revision/deletion.
5. **Repair known weak paths.** Omi's reviewed consumer transport can dequeue without storing in particular connected/unsubscribed or failed-send paths, and notification completion is weaker than durable phone storage. AURA must keep local-first capture and explicit host receipts. Do not adopt automatic loss of unsynced audio, credential-bearing diagnostic logs, or delete-before-rename file publication. See the [bounded source findings](../research/omi-review.md#firmware-findings-worth-learning-from).

These are designs derived from the reviewed source. Omi's documented “locked” contracts are not by themselves proof of deployed correctness, and its consumer nRF5340 firmware is not a compatible nRF52840 binary.

## Hardware decisions required before pin/placement freeze

| Interface/resource | A04 requirement | Reason and remaining verification |
|---|---|---|
| MCU/module | Retain Raytac MDBT50Q nRF52840 family unless root hardware review changes the exact part | A03 software baseline and Omi dev-kit codec experience are relevant; actual codec + security image fit remains required |
| PDM | Shared CLK and DIN for opposite-clock-edge stereo microphones; software rail enable; independent physical rail disconnect and sensed switch position | A03 uses two PDM edges on one DIN, not two independent DIN pins. Check new microphone startup, voltage, clock/rate and physical acoustic ports |
| Audio flash | External nonvolatile audio store, with bounded program/erase/read latency and explicit recovery behavior | Streaming/encoding/DMA must not be blocked by a full-volume scan or unbounded erase; validate program-while-read restrictions and scheduling |
| Update staging | Captured U10: **MX25R3235FM1IL0, 32 Mbit / 4 MiB serial NOR**, reserved for MCUboot secondary image/metadata | Current custom NAND driver is not assumed available in the bootloader. Confirm the selected NOR's driver, voltage, JEDEC/SFDP behavior and boot-time pins on the actual board |
| Flash map | MCUboot, primary image/trailer, persistent owner/identity/settings; secondary NOR/trailer; build-time slot limits | Choose MCUboot swap/update strategy and sector compatibility explicitly. Do not publish a partition map before building the real codec/security image |
| Shared I²C | Gauge, haptic and selected charger; distinct compatible addresses/levels and pull-up budget | Check exact chosen charger interface and reset defaults; no firmware-only reliance for battery thermal protection |
| Control GPIO | Capture, physical privacy position, microphone enable, default-inactive charging and haptic enable; optional charger fault/IRQ if selected | Boot, watchdog reset, transport command or crashed phone cannot enable capture against physical privacy or unsafe charging |
| Indication | Hardware-coupled recording/privacy indication plus firmware status; tactile haptic if qualified | Visible recording indication cannot depend solely on a responsive app; haptic meaning must not imply data committed before it is |
| Service/test | Accessible SWDIO/SWCLK/RESET/GND/VTref and testable rails/storage buses | Factory identity/provisioning, signed recovery, measured power, programming and first-article fault isolation |
| RF/clock | Antenna all-layer/case/metal keepout; selected clock accuracy and calibration | Phone compatibility, BLE interval/PHY choices, body/chain effects and idle power must be measured |

The [MCUboot design](https://docs.mcuboot.com/design.html) documents distinct bootloader/primary/secondary flash areas and strategy-dependent sector/trailer requirements. This requires a real A04 flash map and power-interruption test, not just adding “OTA” to firmware configuration. Inference for AURA: a known NOR driver is a lower-integration-risk staging path than introducing the custom NAND journal driver into the bootloader. It is still unqualified until built and tested.

No pin numbers are assigned here: the fresh KiCad MCP schematic is the authority. Export its mapping into the A04 devicetree, production test plan and wiring guide, then run a cross-check against that exact schematic/BOM revision. Do not reuse A03 GPIO assignments merely because they compile.

## Proposed v2 archival contract

This is **experimental version 2**, separate from the deployed v1 UUID/command contract. Do not send these bytes to A03 or silently relabel existing recordings. The frame archive is independent of the eventual BLE characteristic/fragment transport. All numeric fields are little-endian. Unknown versions, codecs, flags, reserved bits and inconsistent lengths fail closed.

### Immutable capture manifest — 56 bytes

| Field | Encoding | Meaning |
|---|---|---|
| Magic, version | `4s`, `u8` | `AUR2`, `2` |
| Codec, channels, reserved | `u8`, `u8`, `u8` | `1` PCM16LE / `2` Opus; mono `1`; reserved `0` |
| Device ID, capture ID | `16 bytes` each | Nonzero 128-bit values; capture ID generated and committed before recording begins |
| Sample rate, frame samples | `u32`, `u16` | Initial supported profile: 16000 Hz, 160 or 320 samples per frame |
| Capture start, time source, reserved | `u64`, `u8`, `u8` | Epoch milliseconds; `0/0` means unknown; nonzero time/source `1` means host synchronized; reserved `0` |

Source identity is `{device_id, capture_id}`. Device identity must be provisioned, persisted and bound to the authenticated owner during physical pairing. Random capture IDs require a hardware CSPRNG and durable START record before any audio; retry reuses the same identity. This binary identity is **not authentication**, and must not be advertised openly as a tracking identifier. The transport must bind a peer/session cryptographically to the provisioned identity. Time never silently becomes upload time; future clock corrections are separate derived metadata, not a rewrite of the committed source manifest.

### Audio and bookmark packet — 22-byte header, payload, 4-byte CRC

| Field | Encoding | Meaning |
|---|---|---|
| Magic, version, kind | `4s`, `u8`, `u8` | `AFR2`, `2`, audio `1` / bookmark `2` |
| Sequence | `u32` | One contiguous sequence for audio and bookmark records; starts at zero |
| Sample offset | `u64` | Audio begins at the prior audio end; bookmark addresses a point at or before the committed end |
| Sample count, payload bytes | `u16`, `u16` | Audio count equals manifest frame size; bookmark has zero count/bytes |
| Encoded payload | `0..1275 bytes` | Opaque Opus packet or exactly `sample_count × 2` PCM bytes |
| CRC32 | `u32` | IEEE CRC32 over the entire header and payload; detects header as well as payload corruption |

The reference bounds sequence count at 1,000,000 and default encoded bytes per capture at 256 MiB. Production firmware must split long sessions before its configured journal/sequence/byte limits while keeping a parent-session link. An Opus frame parser/decoder must separately validate the negotiated profile and reject malformed encoded audio; CRC alone does not prove valid Opus. The last partial frame requires a finalize/end-trim field before this format can be frozen; the current reference accepts only complete 10/20 ms frames. Do not pad and silently claim the padding was spoken audio.

The eventual transport negotiates MTU, maximum fragment length, window/credits and supported codecs. Large archive packets are fragmented; the reassembler must cap memory, bind stream/sequence/offset, reject overlaps/conflicts, time out incomplete packets, and never ACK a fragment as a durable whole packet. Capability negotiation, BLE fragmentation and the MCU implementation remain required, not implemented by this module.

### Committed receipt — 90 bytes

| Field | Encoding | Meaning |
|---|---|---|
| Magic, version, flags | `4s`, `u8`, `u8` | `ACK2`, `2`, bit 0 finalized; all other bits zero |
| Device ID, capture ID | `16 bytes` each | Bind receipt to the source and owner-authenticated connection |
| Next sequence | `u32` | All archive packets below this value are committed contiguously |
| Encoded byte count, audio sample count | `u64`, `u64` | Audio payload bytes and samples, excluding bookmark payload/count |
| Archive chain digest | `32 bytes` | SHA-256 chain defined below |

`H0 = SHA256(manifest_wire)`. For each complete archive packet `Pi`, `H(i+1) = SHA256(Hi || Pi_wire)`. The receipt covers the immutable manifest, ordering, frame headers, encoded bytes and bookmark positions. This is a hash chain, **not** the SHA-256 of concatenated audio and **not** a signature/MAC. TLS/BLE owner authentication and transport protection remain necessary. Finalization compares the device's final identity/counts/digest with the host's independently accumulated state.

The host reference stores packet bytes and their receipt in one SQLite transaction using rollback journaling and `synchronous=EXTRA`. It returns an ACK only after the transaction exits successfully. Before a new or replayed receive ACK, and on restart/finalization, it re-reads checksums, continuity and the digest under the same database transaction. This prevents an intact replay from acknowledging another already-corrupted/missing packet. Identical replay is idempotent; conflicting replay is an error that preserves the first source. Finalized captures reject additional data. Full/damaged/read-only storage cannot produce a successful new receipt.

[SQLite's synchronous documentation](https://www.sqlite.org/pragma.html#pragma_synchronous) explains the EXTRA rollback-journal directory synchronization behavior. Durability still depends on the filesystem, operating system and storage honoring flushes. The receiver is single-owner, intended for a local filesystem and has not been benchmarked on phones. It does not encrypt the database, schedule background work, decode audio, upload, reclaim device storage or issue Bluetooth commands. Per-packet transactions and full-prefix verification are a correctness reference: repeated full scans have quadratic aggregate cost over a growing capture. Production batching/integrity checkpoints need separate fault tests and throughput measurements while retaining the commit-before-ACK boundary. This implementation is not a production-speed streaming claim or protection from a compromised host that fabricates both source and receipts.

**A receipt is not a DELETE command.** Device retention policy must distinguish replay position, a complete verified host copy, user deletion and reclaim eligibility. A durable phone copy can still be lost with that phone. Initial retention remains explicit verified deletion; opt-in automatic reclaim requires a visible retention policy, power-cut-safe segment garbage collection and recovery tests. Never substitute notification transmission completion for an application receipt: [Zephyr's GATT API](https://docs.zephyrproject.org/latest/services/connectivity/bluetooth/api/gatt.html) defines transport callbacks, not a remote application/database commit.

### Remaining protocol work before freezing v2

- Partial final-frame trim, interrupted-capture seal, clock correction and long-session linkage.
- Authenticated device/capture/session binding, ownership transfer/reset and confidentiality at rest.
- Capability/service UUID negotiation, BLE packet fragmentation/credits, read-while-capture scheduling and backpressure.
- Firmware persistent hash/sequence state, wear-aware acknowledged-segment reclaim and bounded startup inventory.
- Durable mobile import/export container, shared v2 fixtures using the now-available real Opus encoder, interoperable C/Dart/Swift/TypeScript fixtures and a real device loop.
- Signed OTA service with board/image identity, rollback policy, power/state checks, interruption recovery and key provisioning.

## Memory, tasks and interoperability contract

The existing Convex schema stores notes with owner, title, transcript, summary, actions, tags, recorded time and context consent. A04 needs stable `captureKey`, immutable source revision, time confidence, transcript segments, model/method/version, correction history and source spans on every derived suggestion. Separate authentication tokens from capture identity: current ingestion prefixes source IDs with token IDs, so credential rotation can duplicate one recording. Required migration preserves owner isolation and deduplicates stable capture keys without erasing legitimate distinct captures.

A retrieval request must hydrate candidates from current authoritative records and enforce owner, consent, archive/deletion and revision state before returning text. Context search includes explicit pagination/truncation information and source links; “20 recent notes” must not masquerade as complete archive retrieval. A model reads captured text as data, never as authorization to call tools or change privacy. Accepted tasks have a user decision record and source span; extraction retries do not create another accepted task. Retraction prevents future retrieval, but cannot recall a context pack already pasted into a third-party chat.

External interfaces remain layered: clipboard/Markdown/JSON export for any chat, authenticated read-only MCP where the client supports it, and explicit user-authorized adapters for richer integrations. A “connect to ChatGPT/Claude/Gemini/Grok” button needs a tested supported method and honest fallback; an unverified vendor deep link is not interoperability. Credentials stay in secure client/transport configuration, not model-visible tool arguments or diagnostics. No upstream backend or production account is required to use AURA's independent Convex service.

## Release gates and execution order

1. **Hardware contract:** exact KiCad MCP schematic/BOM/net/pin mapping, charger/dock/NTC choices, module/antenna keepout, serial NOR staging and assembly tolerances agreed by actual artifacts. Root owns these files.
2. **A04 firmware bring-up:** new board target from the schematic, rails/storage/PDM/controls, truthful status, flash partitions, safe defaults and actual ARM build. A03 artifacts retain their identity. No charging or haptic qualification flag is enabled from a software test alone.
3. **Codec and archive:** actual Opus build/notice and encoded host fixtures now exist in the isolated experiment; remaining work includes physical timing/stack, listening/transcription comparison, bounded journal startup and concurrent capture/transfer, and v2 reference ported to firmware with shared fixtures and fault injection.
4. **Mobile loop:** native BLE recovery owner, durable source/receipt/outbox, foreground correctness then actual OS background qualification; local playback, timestamped transcript and bookmark navigation. A timer is not proof of background execution.
5. **Portal/AI:** deployed Convex auth/recovery/deletion, immutable provenance, stable ingestion identity across token rotation, searchable current-consent context, reviewed tasks and tested client adapters. Required account/terms steps cannot be replaced by a local mock.
6. **Security and updates:** authenticated ownership, protected storage, production signing/debug policy, rollback and update fault tests; export/delete/revoke/lost-device flows.
7. **Physical qualification:** assembled A04 plus exact printed case/dock, real battery/charge thermal faults, power/audio/RF/comfort/runtime testing and documented first wear. CAD topology and zero ERC/DRC do not prove these.
8. **Launch consistency:** all downloadable fabrication/print/firmware files, website/portal/video/readme, license notices, versions and documented claims match that qualified unit. Publish all work on GitHub and deploy website services with Vercel. No GitHub Actions.

The acceptance artifact is a requirement-to-evidence matrix with links to actual outputs, exact revision/hash, fixture or physical configuration, result and remaining limits. A green host test, generated manifest or product render must never stand in for an unperformed physical, mobile, cloud or security gate. The active goal remains unfinished until the full requested end state is true and verified.
