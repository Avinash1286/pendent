# AURA A03 native prototype project

Open **`aura-a03.kicad_pro` in KiCad 10**. This directory is the paired editable PCB and schematic used for the manufacturing exports. The working routing record remains in `../output/aura-a03-native-routing.kicad_pcb`; the original native schematic reconstruction remains in `../output/aura-a03-electrical.kicad_sch`.

The paired project preserves the verified copper and pads, links every footprint to its actual schematic sheet/symbol UUID, and uses project-relative `AURA_PCB` snapshots. Schematic footprint fields match those snapshots. The 37 intentional NC pads receive their schematic singleton net names while remaining physically isolated; internal numeric net codes may change. `project-linkage.json` records the source and packaged board hashes, unchanged routed geometry and unchanged assignments of all 208 intended connected pins. The source paths follow [KiCad's native netlist identity convention](https://docs.kicad.org/doxygen/common_2netlist__reader_2kicad__netlist__reader_8cpp_source.html).

After editing this paired project, regenerate its exports directly. Rebuilding the tscircuit placement does **not** reproduce the completed native routing and must not overwrite it. Review proposed changes in KiCad's Update PCB from Schematic dialog before applying them; preserve the paired UUIDs and exact snapshot land patterns.

## Manufacturing status

These are connected **prototype fabrication and assembly-review files**. Read `review/manufacturing-checks.json` and `review/drc.json` before submitting them. Native ERC, schematic parity, board connectivity and bare-board DRC each have **zero findings**. The complete DRC report retains **78 `courtyards_overlap` errors** for assembly review. This is not an assembly-approved or qualified consumer-device release.

| Directory / file | Purpose |
| --- | --- |
| `fabrication/gerbers/` | Four copper layers, front/back mask and silkscreen, routed outline and Gerber job metadata |
| `fabrication/drills/` | Separate metric plated/nonplated Excellon files, drill maps and tool report |
| `fabrication/aura-a03.ipc` | IPC-D-356 electrical test netlist |
| `assembly/stencil/` | Separate front/back solder-paste Gerbers; stencil/process review required |
| `assembly/bom.csv` | 57 component candidates with MPNs; the four custom copper-contact features are excluded |
| `assembly/component-centres.csv` | Component body/reference positions and source rotations, corrected for the converter origin offsets |
| `assembly/native-footprint-origins.csv` | Raw KiCad origins for audit; includes custom contacts and must not be substituted blindly for component centres |
| `review/board-layers.pdf` / `review/schematic.pdf` | Readable board layers and six schematic sheets |
| `review/erc.json` / `review/drc.json` | Native, unsuppressed check output |
| `review/native-smd-pad-spacing-audit.json` | 25,158 different-net SMD pad pairs checked against 0.15 mm; zero violations |
| `review/native-via-aperture-audit.json` | 177 vias and 88,500 comparisons against actual SMD copper/paste; zero intersections |
| `review/manufacturing-checks.json` | Final export scope, via inventory and file hashes |

All fabrication Gerbers, Excellon drills and component-centre coordinates use the board centre as origin, with positive Y toward the necklace bail. Do not mirror the bottom drill file or apply an additional origin offset. Confirm component zero-angle conventions, underside contact soldering, stencil apertures, panel rails and dense-placement acceptability with the selected assembler.

## Board specification

- Outline: 24 × 42 mm, R10 corners, nominal 0.8 mm FR-4, four copper layers.
- Stack: **JLC04081H-3313** — 35 µm outer copper / 99.4 µm 3313 prepreg / 15.2 µm inner copper / 500 µm core / 15.2 µm inner copper / 99.4 µm 3313 prepreg / 35 µm outer copper. Material sum 0.7992 mm, nominal finished-board order 0.8 mm. No controlled-impedance claim is made.
- Finish: ENIG; green solder mask; white legend. Use a nonconductive enclosure finish over the antenna region.
- Authored minimum trace width 0.10 mm, copper spacing 0.12 mm, hole-to-copper 0.20 mm, hole-to-hole 0.25 mm and copper-to-outline 0.30 mm. Actual different-net SMD pad spacing is separately checked against 0.15 mm.
- Routing vias use **175 plated 0.20 mm drills and two plated 0.15 mm drills**; the microphones also require two 0.50 mm NPTH holes. Order capability for these actual mixed tools, not a blanket 0.20 mm minimum. The smaller tool can incur a supplier surcharge. Vias are tented; no epoxy fill or copper cap is claimed.
- Ground lands use solid connections. Account for thermal mass in stencil/reflow and exposed-pad soldering; do not assume default thermal reliefs.
- The top antenna exclusion applies to copper on all four layers. Chain, enclosure, battery and wearing-position RF tests remain outstanding.

The stack and limits were checked against [JLCPCB's published capabilities](https://jlcpcb.com/capabilities/pcb-capabilities), its [stackup calculator](https://jlcpcb.com/impedance), and [component-spacing guidance](https://jlcpcb.com/help/article/minimum-spacing-for-smd-components). The preserved stackup response is `../sources/jlc-4layer-08mm-stackups.json`. These sources do not constitute factory approval of this particular design. This small board needs supplier-approved panelization and assembly access.

## Prototype bring-up

Use the [firmware bring-up guide](../../firmware/README.md) with current-limited supplies and verified parts. Charging and haptics remain disabled in the distributed firmware pending measurements with the selected battery, NTC and actuator. Battery voltage tolerance, thermal cutoff, audio, RF, physical fit and power consumption remain unqualified. The PCB contacts and alignment jig are supplied; a complete charging-dock production design is not included.

## Reproduce the package

Use KiCad's Python, which includes `pcbnew`, and KiCad 10's CLI. From `hardware/`, after a verified native routing/library freeze:

```powershell
$boardHash = (Get-FileHash output/aura-a03-native-routing.kicad_pcb).Hash
& 'C:/Program Files/KiCad/10.0/bin/python.exe' scripts/pair-native-project.py --expected-sha256 $boardHash
& 'C:/Program Files/KiCad/10.0/bin/python.exe' scripts/audit-native-pad-spacing.py --board native/aura-a03.kicad_pcb
& 'C:/Program Files/KiCad/10.0/bin/python.exe' scripts/audit-native-via-apertures.py --board native/aura-a03.kicad_pcb
& 'C:/Program Files/KiCad/10.0/bin/python.exe' scripts/export-native-package.py
node scripts/package-status.mjs
python scripts/package-native-archive.py
```

The pairing step is for rebuilding the packaged project from the frozen working sources; it overwrites generated files in this directory. For subsequent edits in the paired project, rerun the two clearance audits and the exporter without pairing again. The exporter rejects stale audit hashes and fails on unconnected nets, schematic mismatch, ERC findings or non-assembly DRC errors. The final commands verify file hashes and rebuild the portable prototype archive. These commands do not purchase boards, submit files to a factory, or deploy software.
