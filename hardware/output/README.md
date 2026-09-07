# A03 engineering outputs — unreleased

**This directory does not contain a fabrication-ready PCB release.** Do not order the placement export or standalone session.

| File | What it establishes |
|---|---|
| `engineering-package-manifest.json` | Byte hashes for 37 source/output files, explicit unreleased status and current routing/ERC evidence |
| `design-manifest.json`, `logical-netlist.json`, `logical-checks.json` | 61 authored references, 43 nets and checked logical invariants |
| `aura-placement.circuit.json` | Authored tscircuit placement/circuit data |
| `aura-placement.kicad_pcb` | Four-layer native placement only: zero tracks and vias |
| `export-checks.json` | 208 authored connected logical pins retain the intended numeric-pad net assignments in that placement |
| `kicad-a03-final-placement-drc.json` | 65 non-copper findings and 167 unconnected items; no copper/pad/hole/edge violation in the unrouted placement |
| `aura.kicad_sch`, `kicad-a03-schematic-erc.json` | Native schematic interchange draft; 968 ERC findings, including 220 unconnected-pin errors. It is not a validated connected native schematic |
| `aura-placement.schematic.svg` | tscircuit schematic drawing; drawing appearance is not ERC evidence |
| `aura-a03.dsn`, `aura-a03-routing-inputs.json` | Exact native routing input and source hashes |
| `aura-a03-route-attempt.ses` | First actual standalone A03 route: 542 wire paths / 109 vias, incomplete |
| `aura-a03-route-freerouting-drc.json` | Fresh first-session reload: nine disconnected net groups and one dangling-via warning |
| `aura-a03-route-refine.ses`, `aura-a03-refine-freerouting-drc.json` | Latest refined session: 545 wire paths / 109 vias. Router log: 10 gaps / 4 violations; reload DRC: eight disconnected net groups / one dangling-via warning |
| `aura-a03-routing-status.json` | Latest inspected standalone session, checksums and exact status |
| `aura-a03-route-study.svg`, `.png` | Actual standalone route geometry, explicitly marked unfinished |
| `assembly-plan.svg`, `.png` | Mechanical placement reference; does not display routed copper |
| `assembly-bom.csv`, `cpl-top.csv`, `external-bom.csv` | Candidate assembly/procurement review material; four PCB pad-feature references are excluded from the 57 SMT references |
| `fabrication-review-notes.md` | Manufacturing intent and outstanding release contents, expressly on HOLD |
| `attempts/` | Historical and superseded attempts, not current manufacturing evidence |

See `../../docs/hardware.md` for charging, cell, RF, acoustic, mechanical and software qualification limits. The earlier connector SES import was cancelled without an explanation. No alternative import was performed to bypass it. A standalone routing session is not an independently checked routed KiCad board.
