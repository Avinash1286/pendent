# AURA A04: circular pendant, end-to-end launch objective

Active objective, recorded 2026-09-09: redesign AURA to the supplied circular jewellery reference, create the PCB from scratch using **KiCad MCP only**, update the full codebase and all physical/product assets, perform all necessary electrical/manufacturing/print/functional checks, and deliver an end-to-end launch-ready AI note taker informed by Omi's engineering and features. This objective is not complete.

The previous review turn made progress: companion 0.3.1 and 28 tests, source-pinned Omi analysis, and manufacturer-tolerance evidence showing that A03 needs new placement. A04 begins from repository commit `e9e968c425c558565dc555ccd9f39d2e4c6c0769`.

## Visual and experience requirements

- Circular pale satin recording face, slim polished-looking champagne surround, small central status dash, subtle perimeter illumination, short refined bail and a fine chain/alternative breakaway cord.
- Starting mechanical envelope: **40 mm body diameter**, thickness **10 mm aspiration pending a verified stack-up**. These are design assumptions, not measured product specifications. Revise openly if exact parts require it.
- RF-transparent prototype materials and nonconductive decorative finishes around the antenna. A metal-like render does not establish radio performance of a metal enclosure.
- Deliberate recording and visible microphone-power state, physical privacy disconnect, accessible tactile controls, useful haptic confirmation, quiet everyday wear, repairable assembly and an easy charging ritual.
- Capture, save, transfer, transcription, context availability and cloud upload must be separate observable states. Do not label an unacknowledged capture as saved.
- Preserve complete original captures and source provenance; summaries, suggested actions and durable AI memory must remain reviewable.

## Engineering brief before CAD

Purpose: battery-powered, skin-adjacent voice/context recorder for personal daily wear. Initial supply architecture is one protected rechargeable cell, a protected 5 V contact dock, regulated low-voltage digital/audio rails and independently qualified thermal charge permission. Exact cell, charging limits, dock protection and operating/peak current budgets are pending datasheet review in `electrical-architecture.md`.

Interfaces: digital microphones, local nonvolatile audio, encrypted Bluetooth to phone/computer, tactile capture/bookmark/privacy/pairing controls, status illumination/haptics, fuel/thermal sensing, SWD/reset and a physical recovery path. Optional voice-activated/continuous modes must be explicit and retain hard privacy indication. AI processing may use the phone/local host/backend; no unsubstantiated on-pendant LLM claim.

Fabrication baseline: ordinary four-layer PCB, approximately 0.8 mm, through vias, no blind/buried vias, real package courtyards and assembly tolerances. Choose component placement and envelope together before routing. The supplier's verified process limits determine final trace/via/clearance rules; no blanket DRC waivers. All pin mappings, polarities and maximum component envelopes require independent checks.

**CAD authority:** all new schematic, symbols, footprints, PCB, placement, tracks, zones, rules and manufacturing-export mutations must use KiCad MCP tools. Shell/Python may inspect and verify files and write non-CAD documentation/test reports; they must not generate or patch PCB or schematic source. A03 remains a historical release. No A03 routed board is used as the new board template.

## Completion evidence required

| Requirement | Evidence that proves it | Current state |
|---|---|---|
| Reference-aligned design | Inspected exterior/interior renders, dimensioned mechanical contract, actual component stack-up | M2 candidate: 43 mm body, 12.2 mm primary depth / 11.2 mm unselected thin-pack variant, both with actual 1.6 mm PCB. Assembled/exploded source renders inspected; original 40 mm study and M1 preserved. No native-placement or physical fit qualification |
| Fresh MCP-native electronics | New project plus tool-authored schematic/board/libraries, exact-MPN pin checks and auditable history | Fresh seven-sheet/72-reference candidate captured; board remains unplaced/unrouted |
| Correct electrical design | Power/current/thermal/logic/analog margins, matching netlist, ERC and independent schematic review | Conservative thermal calculations and pack comparison recorded; 3 net mismatches, 1 ERC error/9 warnings remain |
| Manufacturable PCB/assembly | DRC, actual max-body/tolerance and courtyard checks, verified stack/keepouts, copper/paste/drill audits, supplier CAM/DFM and first article | Not yet complete |
| Printable, assembled body and dock | Watertight STL/3MF/STEP as applicable, units/wall/fit/clearance/fastener/motion checks, physical prints and assembled fit | Both M2 S1 sets contain 17 STL models: 12 polymer parts, three separate hardware forms and two gauges. Mesh/bounds and sampled mechanism/assembly checks cover the revision; steel replaces inadequate resin bending links. Stock, insulation, measured joint/force/stop behavior, native placement, exact pack, complete dock and physical print/assembly qualification remain |
| Firmware on actual hardware | Reproducible build, protocol/storage tests, real microphone/radio/charge/haptic/boot/OTA and fault tests | Monitored PDM driver, bounded audio FIFO, recorder, Opus/archive, owned NAND journal, SPI control-pair adapter and durable release controller implemented. Host checks: 20 driver, 10 adapter, 10 recorder, 25 SPI, 19 journal and 12 storage groups (740 cases), plus 33 receiver tests. Real C/Opus → committed Python receiver/outbox → C release/reuse preserves another recording on modeled NAND. DK ELF includes the storage-owner snapshot reservation; physical audio erase, on-device execution and complete A04 firmware remain |
| Reliable local/mobile context loop | Real-phone capture/sync/recovery, durable receipts, source-linked transcription/search/context, account and permission tests | Current companion suite: 131 tests, including 36 release/outbox tests. Earlier portal checkpoint: 24 tests; actual C archive → local Whisper → Python uploader → Next.js/Convex tested with synthetic speech. Physical transport/mobile/cloud integration remains |
| Omi feature/practice adoption | Source-pinned feature catalogue with implemented/tested/proposed status, privacy/retention choices and full acceptance backlog | In progress |
| Complete premium showcase | Actual A04 models, interactive inside-out/assembly controls, accessible responsive website and Vercel deployment | A03 only |
| Professional launch film | Updated Hyperframes composition, actual A04 geometry/interior/assembly animation, inspected audiovisual export | A03 only |
| Shared reproducible release | Public GitHub source, BOM/manufacturing/print/firmware/media assets, README previews, manifests and build guides | A04 development checkpoint includes source, checks, codec fixtures, Blender studies and fit specimens; manufacturing/launch release remains incomplete |
| Launch readiness | Physical reliability/thermal/RF/acoustic/fit evidence, applicable qualified reviews/compliance, deployable backend and honest product claims | Not yet complete |

“Best in category” is a design ambition. Capture reliability, speech intelligibility, recovery, battery workload/runtime, comfort, privacy, retrieval quality and usability need measurable comparison; a render, benchmark mock or green build cannot establish market superiority.

## Work ownership and persistence

Root owns the single KiCad MCP project/session, integration and releases. Independent agents own electrical evidence, mechanical design and the software contract. Subsystems must share one confirmed geometry/pin/protocol contract before final assets are generated. The goal remains active across turns until the evidence above is complete; physical work and external service prerequisites must not be silently replaced by simulated checks.

Publishing source and Vercel deployment are authorized by the user. GitHub Actions must not be introduced. Real recordings, credentials and signing keys stay private. Physical PCB ordering/assembly and the applicable qualified review are tracked separately from exported files.
