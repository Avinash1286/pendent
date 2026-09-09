# AURA A04 M2 S1 — unpowered hybrid development specimen

**Digital development checkpoint; not a print, powered, wearable or native PCB release.** M2 preserves the circular pale face, champagne-looking polymer finish, fixed luminous perimeter, small flush status dash, bail, face press and separate side privacy control. The source uses millimetre coordinates with Blender `scale_length=0.001`. M1, the original Ø40 study, process coupon and A03 are separate preserved artifacts.

| Scenario | Body diameter × depth | Actual PCB | Controlled maximum cell gauge |
|---|---:|---:|---:|
| [documented-pack](documented-pack/parts-manifest.json), primary render |43 × 12.2 mm|Ø35.2 × 1.6 mm|26 × 21 × 4.3 mm|
| [thin-cell](thin-cell/parts-manifest.json), unselected goal |43 × 11.2 mm|Ø35.2 × 1.6 mm|26 × 21 × 3.3 mm|

The documented depth accommodates the source pack's 4.3 mm thickness allocation; that pack is **unapproved**. The 3.3 mm pack remains unselected. Neither scenario uses the unauthored 0.8 mm PCB target. Both include the full 0.4 mm growth reservation as a solid, plus a 0.10 mm dielectric allocation and 0.05 mm free separation. Growth allowance, backing, PCM/tab envelope and supplier protection remain unqualified.

## What changed from M1

The integral rear cup loads from the front. A removable rounded-thread polymer bezel provides the front aperture and outward face stop. Its stationary collar seats on the cup; the carrier seats on three independent cup shoulders. The bezel captures that carrier. Three lower PCB posts and matching upper feet with measured foam/shims establish the PCB plane without using the cell as a support. A localized upper radio relief clears the restored 0.7 mm face skirt through full press. The flush dash has no material below the face-back plane.

The carrier has separate face stops at 0.6 mm travel and a nominal 0.25 mm shoe stop. A compliant cartridge separates face movement from the switch. Two separate keeper strips have positive lower rail ledges: their sampled subassembly path slides 3.5 mm, then moves rearward 5 mm to clear the face flange. A separate stationary post blocks each strip after face installation. The previous U crossbar would cross the broader stationary stop arms during face press, so S1 removes it. These are geometry changes, not claims of measured force or strength.

## Files and verification

Each scenario contains **12 polymer-part STLs, 3 separate hardware-form STLs and 2 unpowered gauges**, a source assembly BLEND and a manifest with full XYZ bounds, assembly-to-export translations, file hashes and world-geometry hashes for every modeled part, bound and soft allocation.

| Prefix | Individual specimen |
|---|---|
|01|Open-front rear cup, bail, integrated hollow acoustic ducts, sensor pocket and three PCB seats|
|02|Removable threaded bezel with two front service-pin sockets|
|03|PCB clamp carrier, guides, face stops, independent shoe stops and keeper withdrawal stop|
|04|Captive pale face with local radio relief, cartridge rails and three full-area return-pad bosses|
|05 / 06|Flush status window / separate fixed diffuser|
|07 / 15|Separate left and right sliding keeper strips|
|08|Separate 0.30 mm candidate stainless shoe; form gauge, not a resin print|
|13 / 14|Separate lower stainless stiffener / measured insulating contact pad; hardware forms|
|09 / 10|Side privacy fork / replaceable keeper with measured stop channel|
|11 / 12|Dock contact access carrier / sensor retainer|
|90 / 91|Unpowered board gauge / maximum pack gauge|

Both [mesh audits](documented-pack/mesh-audit.json) pass 17/17 specimens: binary STL length/hash, positively oriented connected manifold topology, nondegenerate triangles, and full XYZ bounds within 0.005 mm after the recorded transform. This is an export check, not a printer tolerance or a complete self-intersection proof.

Both [motion audits](documented-pack/motion-audit.json) pass the authored digital checks: 57 rigid and 13 soft solids; all rigid pairs at rest; 25 separately coupled face/shoe/actuator poses; three privacy travel/width cases with 54 directional take-up samples each and actual virtual replacement-keeper geometry; three compressed-soft states; and 17 assembly/subassembly/tool-access paths totaling 679 samples. The bezel path includes 117 helical/axial poses, with 15° thread increments. Linear assembly increments are 0.25 or 0.5 mm. Same-component body/terminal/lead envelope intersections are listed explicitly; unrelated contacts are not waived. The checker uses CSG volume with a 0.001 mm³ threshold. **Finite samples do not establish continuous clearance between samples.**

The proposed populated-board path covers only the explicit maximum component/lead/pad proxies in the manifest. **All 72 native PCB features / 68 purchased PCB references remain unplaced and unverified.** Native board component count is zero at this checkpoint. Storage parts and most small packages are not represented. A pass must not be described as final populated-board fit, RF acceptance or replacement-part approval.

## Privacy and capture calibration

The authoritative [CUS candidate review](../../../docs/a04/cus22-candidate-review.md) and [verification JSON](../../../docs/a04/cus22-candidate-verification.json) govern the unassigned Nidec CUS-22TB footprint. M2 uses `CAD X=13.5+source Y; CAD Y=-source X`, all six signal pads, all four anchors, both Ø0.9 NPTHs, body/seating/terminal fields, a locator-height proposal and the full transverse actuator envelope. The nominal actuator centre is X 14.85. The tolerance envelope X 14.10..15.60 becomes X 13.95..15.75 with the provisional locator allowance. Locator height, anchor electrical identity, source-view interpretation and native adoption remain open. The native JS202 part is unchanged and does not fit this thin candidate stack.

The old M1 upper-right notch at (16.5, 6.5), radius 3.05, clips an anchor by about 0.568 mm; it is absent from M2. Nominal corrected signal copper still leaves 0.600 mm to the unnotched circular board, against a 0.500 mm copper-edge rule. This 0.100 mm margin is not a tolerance approval.

The fork's rigid gap G is 2.0 mm. For measured switch stroke T and lever width w, required external stroke is `E=T+G−w`; the keeper channel is `2.2+E`. The nominal T 1.5 / w 1.3 case uses 2.2 mm external travel and a 4.4 mm channel. Preliminary T 1.3..1.7 and w 1.2..1.4 require 4.1..4.7 mm replacement channels. OFF is CAD−Y; enabled is CAD+Y. The switch supplies its own detents; the external grip has 0.7 mm nominal lost motion and no separate detents. Actual asymmetric endpoint/locator offsets, release/contact timing and allowable overtravel must be measured before selecting the keeper. Stop strength alone cannot prove safe lever travel.

The capture example uses maximum mounted actuator height 2.25 mm, measured rest gap 0.05 mm, 0.25 mm shoe movement and 0.20 mm actuator depression. The separate face stop is 0.60 mm. Electrical travel 0.1..0.3 mm does not establish an allowed mechanical endpoint: measure the exact ordered switch and remake/finish the shoe and stop as needed. The sampled model proves only this calibrated rigid-body example. Four stationary contacts at X −10.3/−3.7 and Y −6.5/−2 surround the actuator center (−7, −4.5). Rear-pair weights of 5/18 each and front-pair weights of 2/9 each are positive and sum to one, so a rigid plane cannot push its center below their common stop plane by pitching. Shoe/support flex, liner or joint movement, datum error and non-coplanar contacts are excluded; the actual actuator endpoint is not measured or approved.

The proposed HT-800 cartridge pad is 6.2 × 6.2 mm, 0.79 mm free, 0.74 mm at rest and 0.39 mm at nominal full press. Three separate return disks are radius 0.7, free 1.1 mm, working 1.0 mm at rest and 0.4 mm at the face stop. Radius 0.9 face bosses cover their complete nominal 1.539 mm² area; alignment/shear still needs testing. Foam preload, nonlinear response, temperature, creep and repeated use are not simulated. [Rogers HT-800 data](https://www.rogerscorp.com/-/media/project/rogerscorp/documents/elastomeric-material-solutions/bisco/english/data-sheets/180-070-ht-800---medium-cellular-silicone.pdf) lists 0.79 mm availability and 41–97 kPa at 25% deflection. Applied to 38.44 mm², that is a **calculated** 1.58–3.73 N, not an installed force measurement. The 6.3% rest preload must stay below the 0.9 N switch minimum; measured actuation must exceed 1.5 N before the chosen stop. The data does not establish either condition for this thin cut pad.

Separate edge slots preserve the central rear wall, and a deeper 3.2 × 0.6 mm rear guide tongue prevents reliance on foam friction for rear capture. Its nominal full-press clearance above the steel is 0.26 mm. A roof-limited pitch section at minimum shoe thickness gives about 0.232 mm vertical retention margin; that is **not** a tolerance approval or a continuous 3D tilt proof. Actual guiding, yaw, coplanarity, wear and dimensional error remain gates. The foam extends beyond the stop-center polygon, so stable four-point reaction under every off-axis press is not assumed.

## Assembly and release gates

Use unpowered gauges first. Inspect the cup and thread; preseat acoustic working gaskets; insert the fork radially through its 6.4 × 1.3 mm assembly opening; lower the measured privacy keeper from the front; install contact carrier, sensor/interface/retainer, pack/growth/dielectric gauge stack, proposed board and carrier with its measured clamp/return pads. Assemble and fixture the deburred lower steel plate and dielectric liner into the carrier from its underside, then lower that held subassembly from the front. The closure captures the root packet; its seating is measured, not an assumed adhesive joint. Bond and finish the insulating shoe contact pad separately. Assemble the window, foam, metal shoe and two keeper strips in the face, using the two-leg keeper path, then lower the face over the guides. Seat the fixed diffuser in the bezel and rotate the bezel on the demonstrated helical path. The reverse sequence is the modeled service route. Free foam compression during assembly, flexible-wire dressing and real connectors remain physical process work.

The sensor cap rests at Z 4.2 and has 0.1 mm travel below the board. Integrated ducts have real Ø1.3 bores, but microphone port datum, gasket sealing, mesh and acoustic response remain proposals. The dock part is an insulating access carrier; selected mating contacts, nose, strain relief and powered dock qualification remain separate. The nonconductive champagne finish, light emission, RF environment, skin contact and bail/chain loads are not qualified by rendering.

S1 supersedes the structurally inadequate 0.30 mm resin shoe and 0.50 mm round resin carrier arms from checkpoint `94caaf9`. The lower load path is a separate 1.00 mm CAD maximum steel form, with 1.2 mm wide arms and a 3.2 mm bridge routed around the microphone. It bears through a dielectric liner on a wall-tied cup bed outside the board and cell. The carrier root cover and threaded closure supply the opposite reaction. Four non-collinear printed 1.3 mm stop posts and 0.6 mm supported caps bear onto this steel; the 0.35 mm local root cover is a supported interface, not a free bending link. The 1.1 mm keeper strips and 0.6 mm ledges remain short supported printed features. No metal is allocated above CAD Y −1.4; that leaves 12.9 mm to the inherited Y 11.5 antenna allocation, without establishing RF acceptance.

The [structural screening](structural-screen.json), reproduced by [structural_screen.py](structural_screen.py), uses catalog properties and proposed static loads. The candidate is cold-rolled **ASTM A666 Type 301 / UNS S30100 half-hard**, explicitly ordered and lot-certified for **0.2% yield at least 110 ksi / 758 MPa**, with E = 193 GPa. Standard production can guarantee tensile strength, yield or hardness; a generic temper label is insufficient. The supplier's 0.02–1.57 mm strip capability encompasses the two thicknesses, but does not establish an available lot, stock width, MOQ or finished-part acceptance. [Elgiloy material data](https://www.elgiloy.com/wp-content/uploads/2024/06/301-Alloy-Stainless-Steel-Data-Sheet-06042024.pdf) and [strip capability](https://www.elgiloy.com/wp-content/uploads/2024/05/ESM-Stainless-Strip-LineCard-DIGITAL-5.30.2024-compressed-1.pdf) support those candidate terms.

The old 0.50 mm resin arm predicts about 307 MPa at 1.5 N; its very large linear deflection is outside the small-deflection regime and signals rejection. Candidate steel screening uses minimum thicknesses of 0.28 mm for the shoe and 0.95 mm for the lower plate. At 1.5 N, the shoe estimate is 0.0104 mm and the centered support surrogate is 0.036 mm before joint compliance. The conservative unequal-load surrogate reaches 0.060 mm at 1.5 N and 0.199 mm at 5 N, also before joint compliance. Higher yield strength does not remove this displacement: E = 193 GPa predicts 3.6% more deflection than the former 200 GPa assumption.

**The annealed-304 candidate is rejected for the proposed 5 N one-arm screen:** about 249 MPa nominal, or 374 MPa after an assumed 1.5 concentration factor, exceeds its 230 MPa reference. For the certified 301 half-hard candidate, the same factored metal screen has a yield/stress ratio of about 2.03. The centered 5 N case reaches about 208 MPa after that factor. These are calculated metal comparisons, not finished-part, arbitrary finger-press, fatigue or switch-endpoint ratings. The assumed stress factor and reaction sharing are not validated. [Outokumpu Core data](https://www.outokumpu.com/en/products/product-ranges/-/media/files/products/core/outokumpu-core-range-datasheet.pdf?modified=20251117111909&revision=025e9931-a1d5-4c8f-8ff5-f881d38916da) supplies the rejected 304 reference; [Formlabs Tough 2000 V2 data](https://formlabs-media.formlabs.com/datasheets/251013-MS-TDS-Tough_2000_V2.pdf) supplies comparative resin values. Neither is a measurement of these parts.

The short root clamp must be tested. A 1.4 mm assumed reaction spacing gives approximately 14 N hold-down at 1.5 N input, and 46.5 N at 5 N input. The centered 5 N case produces roughly 19–20 MPa nominal local bearing. The right-arm case raises hold-down to about 53.3 N and nominal lower bearing to 23.1 MPa. These reactions are recorded rather than treating the lined root as an established fixed support. Printed cover bending, local compression, closure preload, liner creep, off-axis torsion and joint rotation remain unqualified. First use a rigid switch-height gauge in an **unpowered structural specimen**; measure displacement and slip at 1.5 N, then characterize up to the proposed 5 N fixture load only if initial behavior is stable. Do not use a live switch or pack as the proof-load fixture.

The shoe stack has only 0.51 mm between the calibrated actuator gap and working foam. A 0.50 mm stock plate would leave 0.01 mm and is rejected. The separate 0.28–0.32 mm steel candidate leaves a nominal 0.19–0.23 mm for a stiff insulating contact pad **including adhesive**. The 0.21 mm CAD pad is measured and finished per mounted switch; those intervals exclude printed-datum and mounted-height uncertainty and are not a worst-case tolerance pass. Measure the actual roof, steel flatness, actuator and first/last operation, then finish or remake the pad and stop. Reject stacks outside the subsequently validated finishing range.

The lower plate's proposed incoming acceptance is 0.95–1.00 mm and the liner's is 0.08–0.10 mm, giving a nominal 0–0.07 mm shim allocation in the 1.10 mm root packet. Nominal 1 mm stock is not automatically accepted. Measure the actual packet and printed gap, finish the bed and use a controlled root shim to achieve positive closure capture without distortion. The CAD metal-to-board gap is 0.20 mm, or 0.10 mm below the nominal liner; actual PCB warp, print dimensions and native placement must be checked. Steel edges, dielectric bonding, insulation integrity and shim retention are manufacturing work, not resin-print assumptions.

Use a characterized engineering-resin process for the short supported polymer details, with measured coupons, cleaning and post-cure. Preserve the supplied cold-worked temper. Controlled cold blanking or cool machining and deburring are proposed process choices, with minimum section and flatness inspection; the STLs are dimensional form gauges. Do not credit annealing, welding or hot straightening without requalification. Laser/EDM processing needs finished-edge/property qualification; parent-stock yield certification does not qualify a heat-affected edge. Complete metal processing before insulation or adhesive assembly. [Ulbrich explains loss of cold-work strength during annealing](https://www.ulbrich.com/blog/understanding-the-difference-between-annealing-and-tempering/); [Alleima documents welding effects in a 301-equivalent strip](https://www.alleima.com/en/technical-center/material-datasheets/strip-steel/alleima-12r11/). Neither provides universal cutting settings for these parts. The original coupon does not qualify this hybrid joint. Thread torque, anti-loosening, sealing, off-axis presses, switch/foam selection, all 72 native features, supplier pack approval, RF/acoustic/thermal and worn-device testing remain release gates. The rear bail is present in CAD but occluded in the two inspection views; its load, comfort and breakaway behavior remain pending.

## Reproduce

With Blender 5.2 and Python available, run for both scenario IDs:

```powershell
blender -b -t 2 --python build_m2.py -- --scenario documented-pack
python verify_meshes.py --scenario documented-pack
blender -b -t 2 --python check_m2.py -- --scenario documented-pack
blender -b -t 4 --python render_m2.py -- --view assembled
blender -b -t 4 --python render_m2.py -- --view exploded
python structural_screen.py
python engineering_audit.py
python package_m2.py
```

[Assembled inspection](documented-pack/m2-assembled.png) and [exploded inspection](documented-pack/m2-exploded.png) show the actual 43 × 12.2 mm primary source. Render scripts always set `visuallyInspected:false`. Only a separate review of the exact PNG, bound to its hash, can record inspection. [Readiness](readiness.json) checks current source/output hashes and preserves all non-digital release gates as false.
