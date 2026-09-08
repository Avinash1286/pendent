# CUS-22TB privacy-switch candidate

Status: **unassigned land-pattern candidate, not an approved substitution or fabrication release**. KiCad MCP created [the footprint](../../hardware/a04/AuraA04.pretty/Nidec_CUS22TB_Candidate.kicad_mod). The native SW1 still uses JS202011JCQN; the schematic, outline and placement were not changed. This investigation corrects the preserved M1 study rather than silently rewriting its evidence.

## Drawing and interpretation

The [Nidec catalog, page 3](https://www.nidec-components.com/e/catalog/switch/cus.pdf) supplies the CUS-22B outline and lands. `T` denotes reel packaging. The pad drawing is not explicitly labelled with its viewing side. Its asymmetric pins and the neighbouring CUS-12 drawing support a component-side interpretation; this remains a documented inference requiring physical orientation verification.

Origin is midway between locating holes. Source X is right, Y down:

| Lands | Centres in source axes, mm | Size, mm |
|---|---|---|
| 1, 2, 3 | X −2.25, +0.75, +2.25; Y −2.55 | 0.7 ×1.5 |
| 4, 5, 6 | Same X; Y +2.55 | 0.7 ×1.5 |
| MP1–MP4 | X ±3.65; Y ±1.8 | 1.0 ×0.8 |
| Two locating holes | X ±1.5; Y 0 | Ø0.90 NPTH |

The finished-hole requirement is Ø0.90 +0.05/−0.00; a nominal drill in a footprint does not encode or qualify that fabrication tolerance. MP1–MP4 are **our identifiers**, not manufacturer terminal numbers. The catalog identifies a ground terminal in the internal structure but does not explicitly guarantee all four tabs' mutual continuity. Do not assign this footprint to the existing six-pin symbol and silently leave extra tabs floating. Establish the intended shell bond, author the matching symbol through MCP and verify isolation/continuity on incoming parts before adoption.

The nominal body is 6.7 ×4.1 ×1.4 mm. The general ±0.2 tolerance informs a 6.9 ×4.3 ×1.6 allocation. The 0.7 mm offset ends at the actuator **centreline**: transverse nominal offset is `4.1/2−0.7=1.35 mm`. These dimensions come from the same manufacturer drawing; they are not measurements of received parts.

Applying those general tolerances conservatively gives actuator offset1.35±0.30 mm. Including its0.8±0.1 transverse depth yields **CAD X14.10…15.60** at the proposed body centre, before locator/placement/play. Nominal1.5 mm travel gives a preliminary1.3…1.7 mm range. A shell stroke must accommodate lost motion and reach both detents without assuming the switch absorbs excess travel. M1's1.8 mm fork gap and2.4 mm shell stroke can demand1.8…2.0 mm switch motion; its stop/shim design is not qualified. Stop-strength testing is not an overtravel allowance.

## Corrected proposal and M1 errata

For an underside switch centred at CAD (13.5,0), with its actuator offset toward the outer rim:

```text
CAD X = 13.5 + source Y       CAD Y = −source X
Native X = 100 + CAD X        Native Y = 100 − CAD Y
```

The [read-only audit](audit-cus22-candidate.py) lists each predicted native pad coordinate. This is algebra, **not a verified KiCad flip or native placement**; compare the actual transformed lands before accepting either. Commons 2/5 should end at native Y100.75. Under this proposal, the existing electrical contract makes motion toward CAD −Y microphone OFF and +Y enabled.

Three corrections are required relative to M1:

1. `CAD Y=source X` describes the opposite mounting face. Reverse this sign for the proposed rear mounting.
2. The actuator centre must be CAD X14.85, not14.45. The M1 fork therefore needs a 0.40 mm outward shift, followed by a new tolerance and motion check.
3. The upper-right M1 outline notch intersects an anchor land. At notch centre (16.5,6.5), radius3.05, its distance from the nearest pad corner is2.482 mm: **0.568 mm penetration**. The earlier0.600 mm copper-to-circle margin excludes that notch and cannot justify the M1 proposal.

The rectangular8.9 ×7.2 courtyard includes0.3 mm outside the pad envelope. Its empty outer corners extend about0.070 mm beyond the unnotched circle at the proposed placement. This is a packaging finding to resolve, not permission to shrink a courtyard to silence it. M2 must establish its own actual outline and full-body/terminal clearances.

## Reproducible checks and remaining gates

Run from the repository root using KiCad's Python:

```powershell
& 'C:/Program Files/KiCad/10.0/bin/python.exe' docs/a04/audit-cus22-candidate.py
```

[The JSON report](cus22-candidate-verification.json) binds the footprint, native board and audit hashes. It checks native parsing, all ten numbered lands, two unnumbered NPTHs, sizes, coordinates, layer/type/paste declarations and the two outline rectangles including shape/stroke. It also calculates the proposed circular-edge and old-notch margins. The script only reads CAD and writes its JSON report. `landPatternCheckPass` explicitly excludes physical envelopes, stencil suitability, footprint attributes and orientation marking.

Native parsing reports footprint **attributes0**, so the footprint is not classified `FP_SMD` despite its ten SMD lands. Exports filtered to SMD-classified footprints may omit it. No silk graphics, pin1 marker or actuator/detent graphic were created. These remain **assembly/export gates**. The exposed footprint-creation schema has no footprint-attribute or orientation-marking option; the inspected component editor only changes reference/value/footprint assignment. No unsupported argument, file patch or alternative approval path was used to change these fields.

The MCP library-name lookup returned no footprints for `AuraA04` and could not retrieve this candidate by name, despite the registered project table and existing files. Native KiCad `FootprintLoad` using the explicit local library path successfully parsed the new file. Project-library resolution and portability remain separate unresolved checks; this was not treated as an invitation to alter global settings.

Before adoption: close the ground-tab/symbol mapping, actual underside orientation, actuator stroke/force/tolerance, all terminal and solder envelopes, assembly access, hole process and populated-board checks. Before fabrication, also resolve the already documented schematic/rules/stackup gaps and complete qualified battery/RF review. A parsed library part is not a routed PCB or a wearable product.
