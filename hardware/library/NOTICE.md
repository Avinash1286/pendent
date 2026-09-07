# Third-party land pattern attribution

Except for the explicitly authored AURA silicon-capacitor land, the `.kicad_mod` files in this directory were copied from the installed KiCad 10 official footprint library. Source: [KiCad official footprint libraries](https://gitlab.com/kicad/libraries/kicad-footprints). License: [CC-BY-SA 4.0 with KiCad library exception](https://www.kicad.org/libraries/license/).

The original files are retained for pad, stencil, annular microphone ground, and courtyard review. `scripts/prepare-library.mjs` extracts pads into `src/footprints.json`. The tscircuit authoring layer preserves pad positions, sizes and right-angle rotations, but currently renders rounded rectangular lands as rectangles. The microphone annulus is rebuilt as a polygon ring to retain the central acoustic opening. Re-exported KiCad libraries and stencil masks therefore require comparison with these originals before manufacture.

`RF_Module.lib` and `Sensor_Audio.lib` were downloaded from the official archived GitHub mirror of KiCad symbols and were used as pin-map crosscheck references. Those files carry the same KiCad library licensing policy.

`AURA_SiCap_1.2x0.7mm_P0.7mm.kicad_mod` is an authored land pattern based on dimensional facts from Murata BBSC Rev.3.00 and its Assembly by Reflow Rev.1.42. It is not an official Murata CAD file. The source index links those documents. It is provided under the repository's license, with manufacturing tolerances and stencil qualification still required.

The unused older 6 × 5 mm WSON file is retained for historical comparison only. W25N01GVZEIG uses the 8 × 6 mm footprint recorded in `src/footprints.json`.
