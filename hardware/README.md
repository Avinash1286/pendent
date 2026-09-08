# AURA pendant electronics · EVT-A03

Start with the [paired native KiCad project and manufacturing guide](native/README.md). It contains the routed 24 × 42 × 0.8 mm four-layer board and readable six-sheet schematic for the 48 × 28 × 10 mm capsule.

**The board is connected; assembly qualification remains open.** Native schematic verification matches 61 references, 43 intended nets, 208 connected pins and 37 intentional NC pins, with zero ERC findings. Final native DRC, exports and their exact limitations are in [`native/review/`](native/review/). Courtyard/assembly findings remain visible. A connected board and valid fabrication files do not establish a qualified assembled wearable.

## Open or manufacture a prototype

Open [`native/aura-a03.kicad_pro`](native/aura-a03.kicad_pro) in KiCad 10. See [fabrication files](native/fabrication/), [BOM, positions and stencil files](native/assembly/) and [review PDFs/reports](native/review/). Read the native manufacturing guide before sending any files to a supplier. Use the matched Gerbers, PTH/NPTH drills and stack specification from the same package.

The native project carries exact per-reference footprint snapshots, portable library paths and schematic/PCB UUID links. The tscircuit export is a placement reference; it is not a substitute for the completed native routing. Keep the native project as the authority when changing copper, and reconcile source/firmware/enclosure contracts when changing circuitry or component placement.

## Reproduce the authored design

```sh
npm ci
npm run build
npm run export
npm run verify-export
npm run verify
```

Node 22+ and the project-local Bun runtime build the authored tscircuit schematic/placement and logical checks. The native reconstruction repairs the converter's electrical-label, NC, electrical-type and library-reference omissions; see the [schematic audit](../docs/schematic-audit.md). The generated `output/aura.kicad_sch` remains a superseded converter diagnostic, not the current schematic.

KiCad MCP was used for native schematic work. Its SES import returned an unexplained cancellation. The user explicitly authorized the source/CLI fallback, after which the native session was imported and the remaining routes, antenna exclusion and ground connectivity were completed. Historical KRT/Freerouting attempts are retained as evidence; they are not the current fabrication files.

## Files and verification

- `src/design.ts`, `AuraPendant.tsx`, `placement-overrides.json`: selected components, logical pin maps, mechanical contract and current component positions.
- `native/`: paired editable release project and its manufacturing/review exports.
- `library/`, `library.pretty/`, `pcb-snapshot.pretty/`: original lands, authored custom contacts/SiCap lands and exact native snapshots. [Attribution](library/NOTICE.md).
- `output/aura-a03-native-routing.kicad_pcb`: frozen working route used to create the paired project.
- `output/aura-a03-electrical.kicad_sch`: original native reconstruction, retained with its independent ERC and exact netlist audit.
- `scripts/pair-native-project.py`, `scripts/export-native-package.py`: native project pairing and guarded export entry points. KiCad's Python provides `pcbnew`.
- `scripts/package-status.mjs`, `scripts/package-native-archive.py`: verify current export hashes and produce the portable [prototype fabrication ZIP](output/aura-a03-prototype-fabrication.zip) with its [checksum report](output/aura-a03-prototype-fabrication-manifest.json).
- `scripts/audit-native-pad-spacing.py`, `scripts/audit-native-via-apertures.py`: actual native copper/paste geometry checks; both accept `--board native/aura-a03.kicad_pcb`.
- [Hardware dossier](../docs/hardware.md), [electrical review](../docs/electrical-review.md), [thermal review](../docs/thermal-review.md): rationale, source evidence and physical qualification work.

Optional routing-analysis scripts use the pinned packages in `requirements-native.txt`, installed into the ignored `tools/python/` directory with Python 3.11. They are dependencies, not design artifacts. The original routing experiments also use [Freerouting 2.4.1](https://github.com/freerouting/freerouting/releases/tag/v2.4.1) and Java 25. The JAR SHA-256 is `251101c3eeac22d7e7dfcf6796603279e5d1000283eb82d8f093780f7afc6aa9`; keep it in `tools/`. It is excluded from Git. See `scripts/route-freerouting.ps1` for bounded execution and optimization settings.

The [firmware](../firmware/README.md) performs local recording, recoverable storage and Bluetooth transfer. The [desktop companion](../companion/README.md) performs local transcription and optional transcript upload to [AURA Notes](../portal/README.md). No language model runs on the pendant. Physical power, battery, audio, RF, fit and security qualification remain outstanding; the supplied firmware keeps charging and haptics disabled pending those measurements.
