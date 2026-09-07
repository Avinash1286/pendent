# AURA pendant hardware · EVT-A03

This is an authored electrical design and placement, **not a fabrication release**. The current A03 board is 24 × 42 × 0.8 mm, with R10 corners and four copper layers, designed for the 48 × 28 × 10 mm capsule. It contains a BLE radio, two PDM microphones, NAND storage, battery power path, independent charge hot cutoff, a physical microphone disconnect and a full-face record control. Consult [`../docs/hardware.md`](../docs/hardware.md) for actual routing, DRC evidence and release blockers.

```sh
npm ci
npm run build
npm run export
npm run verify-export
npm run verify
```

Node 22+ and the project-local Bun runtime are used. `npm run build` creates an unrouted placement reference. The optional `npm run route` attempts KRT; its earlier attempt failed, and is archived without implying copper completion. `npm run export` converts circuit JSON into editable KiCad files and restores the original microphone annular land. KiCad 10 is needed for independent board DRC. The supplied land patterns make normal builds independent of the KiCad library installation; only `npm run prepare-library` needs `KICAD_FOOTPRINT_DIR`.

For standalone routing, install Java 25 and download [Freerouting 2.4.1](https://github.com/freerouting/freerouting/releases/download/v2.4.1/freerouting-2.4.1.jar) into `tools/`. SHA-256: `251101c3eeac22d7e7dfcf6796603279e5d1000283eb82d8f093780f7afc6aa9`. Export the exact current board to DSN through KiCad, then run `scripts/route-freerouting.ps1`. A session file is an unvalidated routing attempt until imported into the matching board and checked independently. The connector declined the previous SES import without providing a reason; this package does not hide that limitation or import through a different path.

The third-party JAR is excluded from the repository. The routing script explicitly disables optimization and bounds job duration. Freerouting 2.4.1 source normalizes `-mt 0` to all available processors, despite conflicting CLI documentation, so this package does not rely on that flag to disable optimization.

- `src/design.ts`: BOM candidates, component pin/net maps, mechanical contract.
- `src/AuraPendant.tsx`: authored tscircuit PCB and schematic.
- `src/placement-overrides.json`: final placement coordinates; positive Y is the necklace top.
- `library/`: original KiCad 10 footprints and an authored Murata silicon-capacitor land; attribution is in `library/NOTICE.md`.
- `output/`: generated circuit JSON, schematic/PCB images, KiCad exports, BOM, placement, and validation reports.
- `output/aura-a03-route-study.svg`: actual standalone session geometry, explicitly unfinished; see the accompanying routing status and DRC reports.
- `output/fabrication-review-notes.md`: unreleased board/assembly intent and the specific files still needed for a reviewed fabrication release.
- [`../firmware/`](../firmware/): compiled ARM firmware and native tests. `hardware/firmware/` contains the earlier interaction reference and contract. The current PCM journal has approximately 66 minutes ideal capacity before other metadata/bad blocks; no hardware-tested recording or completed mobile application is claimed.

AI transcription, summaries, search, and tasks run in a paired phone service or opt-in cloud service. The pendant performs audio capture, local storage, controls, and Bluetooth transfer. It does not run an on-device language model.
