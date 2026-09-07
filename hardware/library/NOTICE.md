# Third-party land pattern attribution

The `.kicad_mod` files in this directory were copied from the installed KiCad10 official footprint library. Source: [KiCad official footprint libraries](https://gitlab.com/kicad/libraries/kicad-footprints). License: [CC-BY-SA4.0 with KiCad library exception](https://www.kicad.org/libraries/license/).

The original files are retained for pad, stencil, annular microphone ground, and courtyard review. `scripts/prepare-library.mjs` extracts pads into `src/footprints.json`. The tscircuit authoring layer preserves pad positions, sizes and right-angle rotations, but currently renders rounded rectangular lands as rectangles. The microphone annulus is rebuilt as a polygon ring to retain the central acoustic opening. Re-exported KiCad libraries and stencil masks therefore require comparison with these originals before manufacture.

`RF_Module.lib` and `Sensor_Audio.lib` were downloaded from the official archived GitHub mirror of KiCad symbols and were used as pin-map crosscheck references. Those files carry the same KiCad library licensing policy.
