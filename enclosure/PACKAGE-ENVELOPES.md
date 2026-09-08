# Internal package envelopes

The A03 mechanical sync replaces the original generic 0402 passive blocks with dimensions from the hardware footprint catalog. Power-package dimensions also follow that catalog; Q1 uses the independently verified plastic-body orientation below. D1/D2 now have explicit presentation bodies. Control, radio, flash, cell and exterior interfaces remain fixed. These are envelope proxies, not manufacturing STEP models or a populated-board fit qualification.

`snapshot_component_bodies.mjs` records dimensions and exact MPNs without changing positions. `sync_hardware_reference.mjs` resolves final hardware source positions only after its caller confirms the hardware owner's routing freeze. `build_aura.py -- --no-render` rebuilds the model and manufacturing meshes. `verify_print_invariance.mjs` then compares all eight STLs with the pre-sync checkpoint using both file hashes and order-independent triangle signatures.

`verify_model_sync.mjs` reads the exported binary GLB independently and checks all 56 package XY positions, **55 exact rotations plus one proven C18 body-symmetry match**, and the local dimensions and heights of the 50 power/passive/diode bodies. Its output is [model-sync-audit.json](model-sync-audit.json); zero unintended deviations remain.

The final C18 source/PCB rotation is **270°** at (−2.05, −13.3); the saved visual body remains at **90°**. This exception is restricted to C18's exact MPN, KEMET C0402C104K4RACTU, an unmarked nonpolar capacitor. [c18-source-sync.json](c18-source-sync.json) records the bounded source correction: all other 60 placements, all 61 logical pin maps and the logical netlist stayed unchanged. PCB pin orientation is not exempted or changed by the model audit.

[verify_c18_symmetry.mjs](verify_c18_symmetry.mjs) decodes the actual C18 mesh in all three GLBs. Each has 216 unique positions and 428 triangles; the complete triangle set and each triangle's shading normals are invariant under a half-turn, with zero measured vertex or normal error. The material is uniform and untextured, and the proxy has no pad or marking geometry. [c18-symmetry-audit.json](c18-symmetry-audit.json) binds this proof to the existing binary hashes. `build_aura.py` reproduces the same canonical 90° body from the 270° source entry. Blender, all GLBs, the eight print STLs, product photographs and the 44-second film remain byte-for-byte unchanged by this orientation-only follow-up.

## Verified maximum dimensions

All dimensions are millimetres, expressed in local package axes before the placement rotation. Lead spans, body bounds, solder lands and assembly courtyards are different quantities.

| Part | Maximum envelope used | Primary source |
|---|---|---|
| C7/C10, KEMET C0603C225K8RACTU | 1.75 × 0.95 × 0.90 body | [Exact KEMET specification](https://search.kemet.com/component-documentation/download/specsheet/C0603C225K8RAC7867) |
| C8, KEMET C0603C475K8PACTU | 1.75 × 0.95 × 0.90 body | [Exact KEMET specification](https://search.kemet.com/component-documentation/download/specsheet/C0603C475K8PAC7867) |
| C17, KEMET C0402C103K5RACTU | 1.05 × 0.55 × 0.55 body | [Exact KEMET specification](https://search.kemet.com/download/specsheet/C0402C103K5RACTU) |
| C18, KEMET C0402C104K4RACTU | 1.05 × 0.55 × 0.55 body | [Exact KEMET specification](https://search.kemet.com/download/specsheet/C0402C104K4RACTU) |
| Q1, Diodes DMG2302UK-7 | 1.40 × 3.00 × 1.10 body; 2.50 × 3.00 × 1.10 conservative body-and-lead sweep | [Diodes datasheet, page 6](https://www.diodes.com/datasheet/download/DMG2302UK.pdf) |

For Q1, the SOT-23 footprint has its long plastic-body axis along local Y. The former catalog envelope did not distinguish this body from its lead span. The maximum-body check found that the earlier R7/C17 row at Y−2.05 had zero or negative clearance to Q1; routing coordination moved that row to provide positive clearance. The historical proposals and their results remain in `placement-sync-proposals.json` and `placement-sync-audit.json`.

## What the focused audit proves

`audit_placement_sync.py` evaluates source body rectangles, using verified maximum dimensions where available. It adds a 0.10 mm vertical solder allowance, then checks intersections with the actual saved front/rear shells, fully pressed face, cell allowance, haptic motor/insulator and radio envelope. Q1 additionally gets a conservative rectangular sweep enclosing all three leads. `--current` audits the saved placement snapshot and writes `placement-current-audit.json` with source hashes.

Other packages, including resistors and D1, retain nominal source-catalog envelopes. No XY placement tolerance or solder-fillet envelope is included. The positive gaps do not prove assembly yield, repair access, printer or molding accuracy, switch motion, seals, RF behavior, temperature performance, battery swelling or safe wear. **Physical qualification remains false.** The final hardware package separately owns copper clearance, courtyards, routing checks and fabrication status.

Exterior product photographs remain valid for an internal-only update. The preceding nine-component update used `render_synced_exploded.py` to refresh the exploded photograph and rerendered the film's assembly sequence. The later C18 orientation-only correction requires no visual rerender because the exported triangle and shading invariance is proved above.
