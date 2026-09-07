# AURA A03 development package

**This is a development prerelease, not a fabrication or consumer product release.**

The design is a 48 × 28 × 10 mm satin-framed capsule with a full black recording face, physical microphone cutoff and necklace bail. The complete repository includes the tscircuit design, Blender sources, eight printable parts, firmware, local transcription companion, Next.js/Convex portal, Three.js showcase and Hyperframes launch composition.

- [Live product website](https://pendent-eight.vercel.app)
- [Launch film](https://pendent-eight.vercel.app/film/aura-launch.mp4)
- [Source, setup and documentation](https://github.com/Avinash1286/pendent)

## Included downloads

The print ZIP contains eight separate STL parts, a fit coupon, dock alignment jig, assembly/printing guides, mechanical drawing and geometry reports. STL units are millimetres. Blender and GLB use metres. The editable `.blend`, firmware HEX/BIN/ELF, and 36-second MP4 are also provided as release assets. Read the relevant guide before using an engineering artifact.

## Verified in this package

| Area | Evidence |
|---|---|
| Enclosure | Nine audited meshes each have one connected component and zero non-manifold edges; 15 nominal envelope intersection checks pass; eight STL files contain actual triangles. No physical fit print was performed. |
| Firmware | Zephyr 4.2.0 / nRF52840 ARM build: 219,108 B flash, 83,452 B RAM; 18 native C tests and five release checks pass. No assembled device was connected. |
| Companion | Twelve tests pass; Bluetooth protocol parsing, CRC recovery, guarded deletion/format, opt-in HTTPS upload and redirect refusal are covered. Local Whisper transcribed a synthetic spoken sample. No physical BLE transfer was tested. |
| Notes portal | Next.js production build and type check pass; 11 unit tests, six real local Convex flows and four Next.js authentication HTTP flows pass. Cloud provisioning is pending Convex integration terms acceptance. |
| Website | Production Vercel deployment, type/lint/build checks, asset checks and 60 model/camera framing cases pass. Browser interaction QA was not performed. |
| Film | 36.000 s, 1920 × 1080, 30 fps; 1,080 decoded frames; 15 layout, 300 motion and 24 contrast checks pass. Original music, English title captions and full source included. |

## Hardware release hold

The board is **not fabrication-ready**. The final standalone session contains 545 wire paths and 109 vias but still has 10 remaining connections in the router. A fresh session check reports eight disconnected net groups and a dangling via. The generated native schematic has 968 ERC findings, including 220 unconnected-pin errors. The routed session was not imported into KiCad because the connector cancelled that action without a reason. No production Gerbers are supplied.

Exact candidate footprints and 208 authored connected pin/net assignments were checked, but that does not clear native schematic connectivity, routed-board DRC, power-return design or manufacturing review. Battery/NTC/charger, RF, acoustic, printed fit and safety qualification remain outstanding. The distributed firmware deliberately keeps charging and haptics disabled until measured qualification; secure boot, signed DFU and audio encryption at rest remain future work.

The notes portal works against real local Convex. Its public cloud backend is not provisioned yet. Context Pack copy/export works with any chat that accepts text or files; the read-only MCP endpoint requires a client supporting bearer headers and does not implement OAuth for browser chat connectors.

Sources, artifacts and validation reports are available publicly. Secrets, private recordings, local database files, installed dependencies and third-party tool binaries are excluded. Website releases use Vercel directly; no GitHub Actions are present.
