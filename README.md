# AURA / pendent

**Be here. Keep the thought.**

An open product-development project for a compact necklace AI note-taking device. Electronics, printable industrial design, chip firmware, local transcription, a Next.js / Convex notes portal, an interactive Three.js showcase and a Hyperframes launch film live together here.

## Project status

**A03 development release.** The software and digital artifacts are usable for development; this is not a manufactured or certified device. PCB routing/import validation is incomplete, so no fabrication-approved board is supplied. The case has printable meshes with geometric audits; real fit, battery, acoustic and RF tests remain. Firmware is compiled for the nRF52840 but has not run on an assembled AURA. The notes portal uses real local Convex; cloud setup awaits account terms acceptance. No orders or payments are accepted.

## Project map

| Directory | Contents |
| --- | --- |
| `hardware/` | tscircuit source, circuit outputs, BOM and validation evidence |
| `enclosure/` | Blender source, editable generator, printable enclosure meshes, GLB and product renders |
| `firmware/` | Zephyr nRF52840 firmware, reproducible tool setup, flashable build artifacts and native tests |
| `companion/` | Bluetooth sync, CRC verification, local Whisper transcription and optional portal upload |
| `portal/` | Next.js / Convex private notes, profiles, Context Pack and read-only MCP endpoint |
| `website/` | Interactive React / Three.js product presentation, deployed directly to Vercel |
| `film/` | Hyperframes composition, original soundtrack and rendered launch video |
| `docs/` | Hardware and product engineering notes |

## Design direction

- 48 × 28 × 10 mm capsule body, 54 mm tall including the bail; 24 × 42 mm PCB.
- A glossy black recording paddle in a satin polymer surround, a bookmark gesture, visible microphone-power indication and a physical privacy slider.
- A physical microphone power disconnect, offline local audio storage and BLE phone transfer.
- Dual digital microphones, a protected rechargeable cell and a magnetic contact charging dock.
- Local computer transcription and optional notes upload are implemented. A mobile companion remains future work.
- 16 kHz mono PCM storage has an ideal capacity of about 66 minutes before bad blocks and metadata; battery runtime is unmeasured.

## Start exploring

- [Product and interaction specification](docs/product-design.md)
- [Hardware source and validation](hardware/README.md)
- [Print and assembly guide](enclosure/PRINTING.md) · [eight-part print kit](enclosure/aura-a03-print-kit.zip) · [editable Blender scene](enclosure/aura-product.blend)
- [Firmware build / flash / bring-up](firmware/README.md)
- [Install the local companion](companion/README.md)
- [Run AURA Notes and connect any AI](portal/README.md)
- [Launch film and reproducible Hyperframes source](film/aura-launch/README.md)

The portable **Context Pack** combines your selected notes, source excerpts, personal background and current goals into reviewed Markdown. Copy or attach it in ChatGPT, Claude, Gemini, Grok, or another chat. Compatible MCP clients can instead read explicitly approved live context through a revocable bearer token. Provider buttons do not send data automatically.

## Publication

Sources and generated deliverables are shared here. Website deployment uses Vercel directly; this project does not use GitHub Actions. Dependencies, signing keys, tokens, private local recordings and database files are intentionally excluded. Each workstream documents reproducible setup and the checks actually completed.

## Upstream tools

[tscircuit documentation](https://docs.tscircuit.com/) · [Blender](https://www.blender.org/) · [Three.js](https://threejs.org/docs/) · [Hyperframes](https://github.com/heygen-com/hyperframes) · [Vercel](https://vercel.com/docs)
