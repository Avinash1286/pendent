# A03 native footprint documentation and library restoration

Applied and verified on 2026-09-08. All 61 native footprints now use a portable snapshot library with restored Fab/courtyard geometry. Native DRC reports **zero library findings, zero back-text findings, zero unconnected items and 78 unsuppressed courtyard overlaps**. The checked working-board SHA-256 is `8fd4df090a35c8fd2b003c2110e75cc9635e77a8a17d073b7ecdd1e5b3b08038`. The script still defaults to an in-memory inspection and writes only a JSON plan unless its guarded `--apply` option is selected.

[restore-native-footprint-library.py](../hardware/scripts/restore-native-footprint-library.py) restores 297 manufacturer Fab/courtyard graphic shapes onto the existing 61 native footprints. It loads each source named by `src/footprints.json` from the preserved `hardware/library` copies, aligns pad 1 at the current board rotation, then requires every numbered pad center to match within 2 nm. All 61 sources currently match exactly. The actual native copper lands, microphone annulus, solder mask, paste features, drilled features, tracks, vias and footprint placements are retained.

Two source-origin offsets matter: the Raytac module body origin is 1.75 mm above the converter's footprint origin; the microphone body origins are 0.2725 mm below their converter origins. Copying graphics at the converter origin would be wrong. The four J contact patterns additionally require left/right reflection into B.Cu. Their converter footprint containers still say F.Cu; this preparation preserves that container metadata and the actual B.Cu lands, and restores the reflected B.Fab/B.CrtYd documentation geometry. A future footprint-container normalization must preserve these physical pad positions.

Application created `hardware/pcb-snapshot.pretty/A03_<reference>.kicad_mod` and assigned `AURA_PCB:A03_<reference>` to each board footprint. Unique per-reference snapshots preserve actual native pad variants rather than assuming identical MPNs imply identical geometry. `output/fp-lib-table` now contains a project-relative `AURA_PCB` entry with `${KIPRJMOD}/../pcb-snapshot.pretty`, preserving the existing AURA entry. Four existing back-Fab contact labels received mirror flags, and stale Fab reference-label positions now follow the actual source body origins after the routing task's placement changes.

The guard requires a current SHA-256 from the routing owner when `--apply` is selected. A second checksum check prevents writing over a board changed during preparation. Before any save, the script asserts unchanged pad identifiers, net assignments, layer sets, positions, orientations, sizes, drills and mask/paste overrides, plus unchanged routed-copper fingerprints. It reloads the saved board to repeat those checks.

Run preparation with the Python shipped with KiCad 10:

```powershell
& 'C:/Program Files/KiCad/10.0/bin/python.exe' scripts/restore-native-footprint-library.py
```

After routing-owner coordination only:

```powershell
$currentBoardHash = (Get-FileHash -LiteralPath output/aura-a03-native-routing.kicad_pcb -Algorithm SHA256).Hash.ToLowerInvariant()
& 'C:/Program Files/KiCad/10.0/bin/python.exe' scripts/restore-native-footprint-library.py --apply --expected-sha256 $currentBoardHash
```

Native KiCad DRC was rerun after application and zone refill. The [complete report](../hardware/output/aura-a03-restored-final-drc.json) contains only the 78 courtyard overlaps. The script does not suppress courtyard or library checks. KiCad 10's convenience footprint-save wrapper could not identify the format of the new empty library; selecting its native KiCad writer explicitly resolved that technical defect before saving the board.

The latest [read-only plan](../hardware/output/native-footprint-library-plan.json), refreshed after the routing owner's passive placement corrections, finds **78 front-courtyard intersections and zero Fab graphic-bound intersections**. All 61 source-to-native pad alignments still match exactly. The initial plan had 80 courtyard intersections and two small Fab-bound intersections around Q1/R7 and Q1/C17; the placement corrections resolved both Fab-bound findings. Courtyard intersections remain assembly-clearance review findings exposed by the restored source shapes. They are not assertions of physical body collisions, and they must be resolved or individually justified through a reviewed assembly process before claiming assembly readiness.

The [applied restoration report](../hardware/output/native-footprint-library-restoration.json) records its input/output board SHA, every source SHA, all aligned body origins, Fab/courtyard bounds and unchanged-pad/routed-copper assertions. Routing changes invalidate that snapshot; regenerate the plan before any later application. Schematic parity is covered separately by the [schematic audit](schematic-audit.md); the preceding route cleanup is documented in the [copper cleanup report](native-copper-cleanup.md).
