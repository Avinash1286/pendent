# AURA EVT-A03 fabrication review notes

**HOLD — engineering intent only. Do not submit the present placement board or standalone session for fabrication.** The session has not been imported into KiCad, copper completion and independent routed-board DRC are outstanding, and battery/RF/assembly qualification remains incomplete. The authoritative status is `aura-a03-routing-status.json` together with `kicad-a03-final-placement-drc.json` and `../../docs/hardware.md`.

## Board intent

| Feature | Authored intent / review requirement |
|---|---|
| Outline | 24 × 42 mm rounded rectangle, R10 corners; no mounting holes |
| Thickness | 0.80 mm finished target; fabricator tolerance and complete enclosure stack must be approved together |
| Copper layers | F.Cu, In1.Cu, In2.Cu, B.Cu; layer functions and continuous return planes are not yet released |
| Smallest routing rule | 0.15 mm track width, 0.12 mm clearance; power widths and thermal paths still require review |
| Through via | 0.45 mm diameter / 0.20 mm drill routing intent; manufacturing drill/plating capability must be approved |
| Board-edge clearance | 0.30 mm minimum intent |
| RF exclusion | No copper on any layer above Y11.95 to the board top Y21; inspect module ground-pad boundary at Y11.95 |
| Contact finish | ENIG candidate on J1 rear contacts; actual contact mating material, wear and skin/environmental exposure are unqualified |
| Acoustic holes | Two Ø0.50 mm NPTH at (−8.5, 8.5) and (8.5, 8.5); no solder, paste, adhesive or cleaning residue may obstruct them |
| NAND exposed pad | Correct ZE 8 × 6 mm WSON, 3.4 × 4.3 mm exposed pad on GND; no exposed vias under the pad |

A fabricator-approved four-layer stackup, copper weights, material, surface finish thickness, soldermask registration, finished-hole tolerance, impedance/return-path strategy and panel tooling are not supplied as approved specifications. A numerical router clearance is not a supplier process qualification.

## Assembly review

`assembly-bom.csv` groups 57 candidate SMT references. `cpl-top.csv` gives their authored body-centre coordinates and rotations. J1–J4 are custom PCB features and intentionally excluded from SMT purchase/placement quantities. `external-bom.csv` lists the battery pack, attached NTC, motor and contact/dock qualification items separately.

The CPL coordinates use board centre (0,0), with positive Y toward the necklace loop. Before assembly, reconcile this convention and rotations against the released Gerber origin and the assembler's machine. Do not infer pin 1 from a body-centre rendering. Review IC, diode, LED, microphone, switch and SiCap orientations against exact manufacturer drawings.

C3/C4 Murata 939113424610-T3N silicon capacitors use an authored mask-defined footprint. Copper is 0.50 × 0.70 mm on 0.70 mm pitch, with intended 0.40 × 0.60 mm mask openings and 0.30 × 0.50 mm paste apertures. Check those dimensions in the eventual manufacturing outputs; approve stencil thickness and process with the assembler. Other nearby Class II capacitors still need the acoustic-placement review described in the hardware report.

The native microphone annular ground land and four paste arcs must be retained. The portable tscircuit ring approximation alone is not the final stencil geometry. Protect the bottom sound ports and qualify reflow, board cleaning, acoustic gasket adhesive and leak performance against the microphone documentation.

The cell candidate is a protected FPBattery/DNK302025 150 mAh pack, with a separate Semitec 103AT-2 NTC. The 20.5 × 28 × 3.3 mm enclosure allowance is an engineering allowance, not an approved assembled pack drawing. Supplier approval of maximum width/thickness/swelling, attached sensor/leads and 4.221 V worst-case charging voltage is required. Charging and haptics remain inhibited in the unqualified firmware build. Do not energize an assembled pack before the thermal and power review gates are completed.

## Required release contents

After resolving the current HOLD, generate and review Gerbers for all copper, soldermask, paste, legend and board-outline layers; separate PTH/NPTH drill outputs; the exact source revision and checksums; IPC netlist if supported; approved stackup and notes; assembly drawings; approved BOM and CPL; stencil files; and a clean independent imported-board connectivity/DRC report. No empty or placement-only copper exports are provided as a substitute for this release.
