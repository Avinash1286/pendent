# Native A03 via, SMD copper and paste aperture audit

Read-only native KiCad geometry audit, 2026-09-08T00:03:13.650842+00:00.

**Board:** `hardware/native/aura-a03.kicad_pcb`.

**Board SHA-256:** `b9ec8ebf1a0afaa7563ed4838e145cebb4f14055f71e25b2dbcb0329b0180064`. The checksum was unchanged before and after the audit. No PCB, aperture, via, rule or library was changed.

**Result:** 177 through-vias checked; 0 drill-to-paste intersections; 0 drill-to-SMD-copper intersections. 0 via(s) have at least one copper-disc or drill intersection.

## All intersections

| Via UUID | Via center (mm) | Net | Diameter / drill (mm) | Target | Layer | Classification | Drill-to-target gap (mm) |
|---|---|---|---|---|---|---|---|
| None | — | — | — | — | — | — | — |

An annulus-only overlap means the via's copper disk intersects the target while its complete drilled opening remains outside. Both the hole disk and hole center are tested separately. A small positive computed gap is not a fabrication-tolerance allowance; the board owner must review and correct marginal geometry.

Normal soldermask tenting is distinct from a specified filled and capped via-in-pad process. Native tenting and filling/capping flags are recorded per via in the JSON; no acceptance of a via-in-pad process is inferred from tenting. This audit introduces no exclusions.

## Geometry and coverage

- 233 front and 14 back SMD copper objects; custom microphone annuli retain their actual holes.
- 231 front and 14 back pad paste apertures, plus 8 independent microphone paste arc strokes.
- Paste sizes use KiCad's resolved per-axis absolute-plus-ratio margin. C3/C4 have −0.100 mm on each edge. The copper-only microphone rings are not incorrectly treated as solid paste rings.
- 88500 native shape comparisons: 43719 copper, 43365 pad paste, 1416 graphic paste. Same-net geometry is included.
- No bounding-box substitute determines any intersection. Native pad shapes and native graphic arc strokes use `SHAPE.Collide` against exact native circles. Distance brackets have 1 nm computational resolution and do not describe production tolerance.

The paste construction follows the [KiCad native plotter](https://docs.kicad.org/doxygen/plot__board__layers_8cpp_source.html). Manufacturing context comes from [JLCPCB rigid-board capabilities](https://jlcpcb.com/capabilities/pcb-capabilities).

## Reproduce

From the repository's `hardware/` directory:

```powershell
& 'C:/Program Files/KiCad/10.0/bin/python.exe' scripts/audit-native-via-apertures.py
```

[Audit script](../hardware/scripts/audit-native-via-apertures.py) · [Complete machine-readable results](../hardware/output/native-via-aperture-audit.json)

This bounded audit does not substitute for trace/via DRC, drill-wall spacing, soldermask-dam checks, assembly-body clearance, or fabrication/assembly qualification. Any later board edit invalidates this exact hash-bound result.
