# AURA A03 — context and assembly edition

**Capture the context of your life.**

[Explore AURA](https://pendent-eight.vercel.app) · [Watch the film](https://pendent-eight.vercel.app/film/aura-launch.mp4) · [Source repository](https://github.com/Avinash1286/pendent)

This edition brings the component placement, Blender model, interactive website and launch film into alignment. The exterior remains a 48 × 28 × 10 mm capsule, 54 mm tall including its necklace bail. The website has three focused chapters: the pendant and its finishes, an interactive assembly explorer, and a short notes demonstration.

This is a development project. No assembled AURA has been tested, and no consumer orders or payments are accepted. Each artifact below has a different verification scope; a rendered model or compiled firmware does not establish physical performance.

## Download and build

| Artifact | Entry point |
| --- | --- |
| Electronics | [Prototype fabrication package](../hardware/output/aura-a03-prototype-fabrication.zip) · [paired KiCad project and manufacturing guide](../hardware/native/README.md) · [tscircuit source](../hardware/README.md) |
| Schematic | [Six-page PDF](../hardware/native/review/schematic.pdf) · [editable paired source](../hardware/native/aura-a03.kicad_sch) |
| Printable parts | [Eight-part print kit](../enclosure/aura-a03-print-kit.zip) · [printing and assembly guide](../enclosure/PRINTING.md) |
| Industrial design | [Editable Blender scene](../enclosure/aura-product.blend) · [device GLB](../enclosure/aura-device.glb) · [mechanical specification](../enclosure/MECHANICAL.md) |
| Device firmware | [Build, flash and bring-up guide](../firmware/README.md) · [release binaries and manifest](../firmware/release/) |
| Local transcription | [Bluetooth companion setup](../companion/README.md) |
| Notes and AI context | [Next.js / Convex portal setup](../portal/README.md) |
| Product presentation | [Website source](../website/) · [live deployment verification](deployment-verification.json) |
| Launch film | [1080p MP4](../film/aura-launch/renders/aura-launch.mp4) · [Hyperframes source and instructions](../film/aura-launch/README.md) |

STL files use millimetres. Blender and GLB use metres. Print the fit coupon and review the assembly guide before committing to a complete enclosure print.

The [release asset manifest](release-assets.json) lists exact download sizes and SHA-256 values. The [PCB archive portability check](native-package-portability.json) verifies all 226 extracted entries and repeats native ERC/DRC successfully with the packaged library paths; the same 78 assembly courtyard findings remain visible.

## Verified digital artifacts

| Area | Evidence and limits |
| --- | --- |
| Native schematic | 61 component references, 43 intended nets, 208 connected pins and 37 intentional NC pins match the authored design. KiCad ERC reports zero errors and zero warnings. [Audit](schematic-audit.md). |
| Native PCB and exports | Zero unconnected items, schematic parity findings and bare-board DRC errors; **78 unsuppressed courtyard overlaps require assembly review**. All 25,158 different-net SMD pad pairs pass the 0.15 mm threshold; 88,500 via-to-copper/paste comparisons have zero intersections. Four-layer Gerbers, separate PTH/NPTH drills, IPC-D-356 netlist, stencil data and 57 component positions are included. [Export checks](../hardware/native/review/manufacturing-checks.json). |
| Enclosure synchronization | All 61 placement records match the hardware source. The GLB audit checks 56 package transforms (55 exact rotations and one proven 180° symmetry equivalent for the unmarked, nonpolar C18 body) and 50 body dimensions. All eight STL files remain byte-identical to the previous A03 print geometry. [Model audit](../enclosure/model-sync-audit.json) · [print invariance](../enclosure/print-invariance.json). |
| Mechanical geometry | Topology checks and 15 case-envelope pairs pass. The focused 10-package audit finds no nominal overlap, contact or solid collision. Physical tolerances, fit, wear, battery swelling and material performance remain unqualified. [Package envelopes](../enclosure/PACKAGE-ENVELOPES.md). |
| Firmware | Zephyr 4.2.0 / nRF52840 build uses 219,108 B flash and 83,452 B RAM. Eighteen native C tests and five release checks pass. It has not run on an assembled device. |
| Companion | Twelve tests pass, and local Whisper transcribed a synthetic spoken sample. Physical Bluetooth transfer remains untested. |
| Notes portal | Next.js production build and type check pass; 11 unit tests, six real local Convex flows and four Next.js authentication HTTP flows pass. Cloud provisioning awaits the account's Convex integration terms acceptance. |
| Website | Type, lint, production build, seven referenced assets and 60 model/camera framing cases pass. The deployed GLB, MP4, captions and poster match the local files by SHA-256. Browser interaction QA was not performed. |
| Film | 44 seconds, 1920 × 1080, 30 fps, 1,320 H.264 frames with 48 kHz stereo AAC. Strict Hyperframes checks report zero findings across 18 layout samples, 300 motion samples and 14 contrast checks. Full encoded-media decoding succeeds. [Film verification](../film/aura-launch/qa/VERIFICATION.md). |

The film's eight-second interior sequence opens five groups of the actual model, holds the inside view and reassembles the device. Its original ambient score, captions, local assets and rendering scripts are included.

## Operation and qualification

The device captures selected audio locally and transfers it over Bluetooth. Transcription runs on a computer using the companion; the pendant does not run a language model. The current 16 kHz PCM journal has about 66 minutes of ideal capacity before metadata and bad blocks. Battery runtime is unmeasured.

The distributed firmware keeps charging and haptics disabled pending measured battery, charger and actuator qualification. RF, acoustics, physical fit, power consumption and an assembled-device bring-up remain necessary. Secure boot, signed DFU and audio encryption at rest are not implemented.

The portal stores private notes in Convex and creates reviewed Context Packs from selected notes and personal context. Copy or attach a pack in any AI chat that accepts text or files. Its read-only MCP endpoint supports clients with bearer headers; it does not implement OAuth for hosted browser chat connectors. Provider buttons do not transfer data automatically.

Source, generated artifacts and validation evidence are public. Installed dependencies, credentials, private recordings and local database files are excluded. The site is deployed directly through Vercel; no GitHub Actions are used. The [earlier A03 release](release-a03.md) remains a historical record.
