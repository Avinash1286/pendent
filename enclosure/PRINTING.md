# AURA A03 — printing and assembly

Start with a mechanical fit prototype. All eight STL parts use millimetres at 100% scale. Closed meshes do not prove process accuracy, material strength, skin-contact suitability or electrical safety.

## Parts and print setup

| Part / quantity | Initial print orientation and process |
|---|---|
| Front frame /1 | Tough SLA/MSLA or comparable detail service; tilt 25–40°, support hidden inner/rear surfaces, protect cosmetic rim and small openings. |
| Rear cup /1 | Tough SLA/MSLA, tilt 25–40° with cavity open; support bail as needed. Keep PCB shelves, clips and fastener bores clean. |
| Record face /1 | Tough opaque resin; supplied face-down atZ0, stem/tabs up. Use a sacrificial support arrangement if direct-bed peel distorts it; tilted printing may improve flatness but needs cosmetic finishing. |
| Privacy slider /1 | Tough resin; flat inner face toward bed and exterior face up in export. Only the exterior part is provided; internal switch coupling remains engineering. |
| Top retainer /1 | Tough dimensionally stable polymer, head atZ0 and shank up. Brittle decorative resin is unsuitable for press-fit retention. |
| Contact carrier /1 | Tough insulating polymer; flat outer face atZ0. Inspect the 0.7 mm body for warp and preserve lead-hole insulation. |
| Fit coupon /1 | Same resin, exposure/cure and orientation class as small features. Print flat and measure after full cure. |
| Passive dock jig /1 | PETG or tough resin, flat bottom.28.5×48.5 pocket gives 0.25 mm side allowance. Contact guides are nominalØ1.4 and must match selected pins. |

Use qualified printer exposure and cure settings;25–50µm resin layers are an initial resolution target. Measure actual XY accuracy. Ordinary 0.4 mm-nozzle FDM is a poor match for 0.3 mm tabs,0.2 mm face gaps,0.62 mm LED opening and 0.96 mm pilots. The passive dock may be printed by FDM separately. Compensate individual dimensions in source rather than scaling the whole assembly to fix a hole.

Nominal walls: face 0.9 mm, rear 1.0 mm, straight sides 1.2 mm. Retaining tabs and clip lips are 0.3 mm prototype features; they may need thickening for the chosen process. The 0.11 mm seam and 0.20 mm paddle gap must remain free after cure/finish. No process-specific tolerance validation has been done.

Coupon datum is the lower-left notch. Top row bores, left-to-right:Ø0.90,0.96,1.02,1.36,2.04. Lower row:7 mm-long slots of widths 1.4,1.6,1.8. Use pin gauges and fit trials; do not force a retainer into a shrunken pilot.

## Mechanical BOM

| Item | Provisional specification |
|---|---|
| Printed parts | One of each eight STLs; coupon is a process aid. |
| Lower case screw | One M1.2-class micro screw, approximately 6 mm under-head length. Select exact pitch/head/profile; head must fitØ2.04 seat. Check engagement and avoid bottoming out. |
| Upper polymer retainer | Supplied printable geometry; approximatelyØ1.0 gripping shank inØ0.96 pilot is an intentional 0.04 mm diametral interference trial. Tune on coupon. |
| Face return gasket | Custom compliant nonconductive gasket, modeled 0.47 mm height. Durometer, preload and compression remain unqualified. |
| Seam gasket |0.08 mm visual reference; select a film/adhesive or redesign a molded seal. No IP rating. |
| Microphone boots /2; lightpipe /1 | Custom compliant sealed interfaces; Blender routing curves are only proxies. |
| Cell insulation |0.05 mm film; fixation must not constrain cell swelling. |
| Haptic carrier |0.05 mm insulating adhesive underØ8.1 motor; validate vibration coupling. |
| Protected cell |150 mAh target; provisional 20.5×28×3.3 allowance, not a qualified cell part. |
| Rear contacts /3 |Ø1.7 visible contact area at 3 mm pitch; actual contact/tail, travel and current rating unresolved. |
| Chain and breakaway | Render uses~0.46 mm wire links. Select a tested wearable breakaway and validate RF. |
| Finish | Fully cured, suitable skin-contact material; nonconductive silver frame and polished black face. Qualification pending. |

## Assembly and checks

1. Wash, cure, deburr and measure empty prints. Verify body 28×48×10, flatness, intact tabs, free face motion and shell mating. Remove supports without unpredictably enlarging gaps.
2. Insert the face from behind the frame. Tabs capture under the ledge; check target 0.35 inward travel against all four stops. Fit the selected return gasket and verify off-axis presses cannot reach components.
3. Start with a nonpowered dummy PCB and cell gauge. PCB24×42×0.8R10 sits on four shelves; clip underside is 0.15 above board top. Check flex/insertion forces without bending a populated board.
4. Fit contact carrier atY−19 below the cell, then select/terminate real contacts and validate polarity/insulation against hardware documentation. The passive dock contains no power electronics.
5. Install qualified cell fixation, insulation, board, haptic film, acoustic boots, lightpipe and engineered privacy linkage. Keep cell/PCM/leads clear of screws, clips and contact tails. KeepY>11.95 free of conductive material near antenna.
6. Close the rear cup with polymer upper retainer and selected lower screw at low torque. Stop if force is needed or the cell becomes a structural spacer. Verify remaining space against supplier swelling limits.
7. Qualify an instrumented test unit for switch feel, recording indication, true mic disconnect, acoustics, thermal shutdown/charge behavior, drop/chain loads and worn RF before treating it as a wearable product.

`assembly-audit.json` reports nominal digital checks only. A physical assembled prototype has not been printed or tested. Battery capacity, control behavior and sealing remain design targets until qualified.
