# A03 native copper cleanup

Completed 2026-09-08 before the final paired-project export. The canonical routed board was promoted only after isolated native KiCad checks and an exact source-hash guard.

**Result:** 109 obsolete copper objects removed, including six vias; five useful track segments shortened to their actual same-net junctions. Native DRC then reported zero unconnected items, zero dangling tracks, zero dangling vias and zero copper errors. No component or pad moved, and no pin assignment, net, pad shape, paste opening, zone boundary or rule exclusion changed.

| Net | Track UUID | Original length (mm) | Final length (mm) |
|---|---|---:|---:|
| CHG_STAT1 | `4ac99085-2ea0-4cfa-9ea6-a45f5cac98b5` | 1.803122 | 1.484924 |
| DOCK_5V | `8027827f-d146-47ac-882a-dd076c3cb64e` | 0.421700 | 0.246700 |
| CHG_STAT1 | `8bb6015b-d451-4192-ad6c-4f703348808d` | 0.401354 | 0.006930 |
| CHG_VSET | `ad606202-069e-44cf-b456-5e601d31ceb0` | 2.687006 | 2.068287 |
| TS_MON | `f54606bd-e040-46de-9771-248abd5a5ca9` | 3.749600 | 2.877900 |

Each shortened endpoint lies on its original track centerline and inside a real native same-net pad, via or track shape. The useful through segment remains. Each trial ran native refill/DRC and rejected any connectivity break, new DRC error or new unrelated warning. One additional segment was temporarily trimmed during testing and was later safely removed; it is counted among the removed objects, not among these five surviving trims.

The first attempt to remove all initially flagged objects together created three missing signal connections. That isolated trial was rolled back. The root cause was a dangling segment whose body also connected at a side junction. Guarded single-item trials identified these cases, and shortening the unnecessary overhangs allowed the remaining obsolete branches to be removed safely.

Full semantic fingerprints compare complete native footprint and pad definitions, net declarations, positions, orientations, custom copper/paste shapes, zone definitions and surviving routed copper. Only reviewed endpoint changes, explicitly identified removals and regenerated zone-fill caches are allowed. A byte-for-byte original-board backup and every trial snapshot remain in the local scratch history.

| Checkpoint | SHA-256 |
|---|---|
| Original connected board | `e7d545cc3f415ab173867c3a12a2160ea83ebf70029fcdac4bd8e99bef82746c` |
| Verified cleanup before library restoration | `14fc416af6ee4921a26d3aabb4ec325199cb3a1578fe77d40d7d0c61209d9ac2` |
| Restored working board after final refill/DRC | `8fd4df090a35c8fd2b003c2110e75cc9635e77a8a17d073b7ecdd1e5b3b08038` |

The subsequent [footprint restoration](native-footprint-restoration.md) resolved all 61 library warnings and four back-text warnings. Its final native DRC preserves 78 source courtyard-overlap findings for assembly review. These findings are not waived, and copper connectivity alone does not establish assembly readiness.

Both [SMD pad-spacing](native-pad-spacing-audit.md) and [via/paste aperture](native-via-aperture-audit.md) audits pass on the restored working-board hash: 25,158 different-net pad pairs at a minimum of 0.150 mm, and 177 vias with zero copper-disc or drill intersections with actual SMD copper or paste apertures.

[Complete cleanup record, including all removed UUIDs](../hardware/output/aura-a03-copper-cleanup.json) · [Native final DRC](../hardware/output/aura-a03-restored-final-drc.json)

The repeatable helpers keep preparation and trials isolated: [initial preparation](../hardware/scripts/prepare-native-dangling-cleanup.py), [junction trimming](../hardware/scripts/trim-native-dangling-overhangs.py), [bounded branch cleanup](../hardware/scripts/finish-native-cleanup-candidate.py), and [hash-guarded promotion](../hardware/scripts/promote-native-cleanup-candidate.py). They do not sync or move schematic components.

The [final paired KiCad board](../hardware/native/aura-a03.kicad_pcb), with explicit stackup metadata and schematic-UUID linkage, has SHA-256 `b9ec8ebf1a0afaa7563ed4838e145cebb4f14055f71e25b2dbcb0329b0180064`. Both geometry audits were rerun against that exact file and pass with the same 25,158 pad-pair and 177-via counts. Its final ERC, DRC and geometry reports are authoritative for manufacturing exports.
