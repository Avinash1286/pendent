# AURA A04 M2 — front-loaded development mechanism

**Digital development checkpoint; not a print, powered, wearable or native PCB release.** M2 preserves the circular pale face, champagne-looking polymer finish, fixed luminous perimeter, small flush status dash, bail, face press and separate side privacy control. The source uses millimetre coordinates with Blender `scale_length=0.001`. M1, the original Ø40 study, process coupon and A03 are separate preserved artifacts.

| Scenario | Body diameter × depth | Actual PCB | Controlled maximum cell gauge |
|---|---:|---:|---:|
| [documented-pack](documented-pack/parts-manifest.json), primary render |43 × 12.2 mm|Ø35.2 × 1.6 mm|26 × 21 × 4.3 mm|
| [thin-cell](thin-cell/parts-manifest.json), unselected goal |43 × 11.2 mm|Ø35.2 × 1.6 mm|26 × 21 × 3.3 mm|

The documented depth accommodates the source pack's 4.3 mm thickness allocation; that pack is **unapproved**. The 3.3 mm pack remains unselected. Neither scenario uses the unauthored 0.8 mm PCB target. Both include the full 0.4 mm growth reservation as a solid, plus a 0.10 mm dielectric allocation and 0.05 mm free separation. Growth allowance, backing, PCM/tab envelope and supplier protection remain unqualified.

## What changed from M1

The integral rear cup loads from the front. A removable rounded-thread polymer bezel provides the front aperture and outward face stop. Its stationary collar seats on the cup; the carrier seats on three independent cup shoulders. The bezel captures that carrier. Three lower PCB posts and matching upper feet with measured foam/shims establish the PCB plane without using the cell as a support. A localized upper radio relief clears the restored 0.7 mm face skirt through full press. The flush dash has no material below the face-back plane.

The carrier has separate face stops at 0.6 mm travel and a nominal 0.25 mm shoe stop. A compliant cartridge separates face movement from the switch. The keeper has actual lower rail ledges: its proven sampled subassembly path slides 5 mm, then moves rearward 5 mm to clear the face flange. The stationary carrier post blocks that withdrawal after face installation. These are geometry changes, not claims of measured force or strength.

## Files and verification

Each scenario contains **12 proposed device-part STLs and 2 unpowered gauges**, a source assembly BLEND and a manifest with full XYZ bounds, assembly-to-export translations, file hashes and world-geometry hashes for every modeled part, bound and soft allocation.

| Prefix | Individual specimen |
|---|---|
|01|Open-front rear cup, bail, integrated hollow acoustic ducts, sensor pocket and three PCB seats|
|02|Removable threaded bezel with two front service-pin sockets|
|03|PCB clamp carrier, guides, face stops, independent shoe stops and keeper withdrawal stop|
|04|Captive pale face with local radio relief, cartridge rails and three full-area return-pad bosses|
|05 / 06|Flush status window / separate fixed diffuser|
|07 / 08|Staged cartridge keeper / measured plunger shoe|
|09 / 10|Side privacy fork / replaceable keeper with measured stop channel|
|11 / 12|Dock contact access carrier / sensor retainer|
|90 / 91|Unpowered board gauge / maximum pack gauge|

Both [mesh audits](documented-pack/mesh-audit.json) pass 14/ 14 specimens: binary STL length/hash, positively oriented connected manifold topology, nondegenerate triangles, and full XYZ bounds within 0.005 mm after the recorded transform. This is an export check, not a printer tolerance or a complete self-intersection proof.

Both [motion audits](documented-pack/motion-audit.json) pass the authored digital checks: 54 rigid and 12 soft solids; all rigid pairs at rest; 25 separately coupled face/shoe/actuator poses; three privacy travel/width cases with 54 directional take-up samples each and actual virtual replacement-keeper geometry; three compressed-soft states; and 16 assembly/subassembly/tool-access paths totaling 668 samples. The bezel path includes 117 helical/axial poses, with 15° thread increments. Linear assembly increments are 0.25 or 0.5 mm. Same-component body/terminal/lead envelope intersections are listed explicitly; unrelated contacts are not waived. The checker uses CSG volume with a 0.001 mm³ threshold. **Finite samples do not establish continuous clearance between samples.**

The proposed populated-board path covers only the explicit maximum component/lead/pad proxies in the manifest. **All 72 native PCB features / 68 purchased PCB references remain unplaced and unverified.** Native board component count is zero at this checkpoint. Storage parts and most small packages are not represented. A pass must not be described as final populated-board fit, RF acceptance or replacement-part approval.

## Privacy and capture calibration

The authoritative [CUS candidate review](../../../docs/a04/cus22-candidate-review.md) and [verification JSON](../../../docs/a04/cus22-candidate-verification.json) govern the unassigned Nidec CUS-22TB footprint. M2 uses `CAD X=13.5+source Y; CAD Y=-source X`, all six signal pads, all four anchors, both Ø0.9 NPTHs, body/seating/terminal fields, a locator-height proposal and the full transverse actuator envelope. The nominal actuator centre is X 14.85. The tolerance envelope X 14.10..15.60 becomes X 13.95..15.75 with the provisional locator allowance. Locator height, anchor electrical identity, source-view interpretation and native adoption remain open. The native JS202 part is unchanged and does not fit this thin candidate stack.

The old M1 upper-right notch at (16.5, 6.5), radius 3.05, clips an anchor by about 0.568 mm; it is absent from M2. Nominal corrected signal copper still leaves 0.600 mm to the unnotched circular board, against a 0.500 mm copper-edge rule. This 0.100 mm margin is not a tolerance approval.

The fork's rigid gap G is 2.0 mm. For measured switch stroke T and lever width w, required external stroke is `E=T+G−w`; the keeper channel is `2.2+E`. The nominal T1.5/w 1.3 case uses 2.2 mm external travel and a 4.4 mm channel. Preliminary T 1.3..1.7 and w 1.2..1.4 require 4.1..4.7 mm replacement channels. OFF is CAD−Y; enabled is CAD+Y. The switch supplies its own detents; the external grip has 0.7 mm nominal lost motion and no separate detents. Actual asymmetric endpoint/locator offsets, release/contact timing and allowable overtravel must be measured before selecting the keeper. Stop strength alone cannot prove safe lever travel.

The capture example uses maximum mounted actuator height 2.25 mm, measured rest gap 0.05 mm, 0.25 mm shoe movement and 0.20 mm actuator depression. The separate face stop is 0.60 mm. Electrical travel 0.1..0.3 mm does not establish an allowed mechanical endpoint: measure the exact ordered switch and remake/finish the shoe and stop as needed. The sampled model proves only this calibrated example.

The proposed HT-800 cartridge pad is 6.2 × 6.2 mm, 0.79 mm free, 0.74 mm at rest and 0.39 mm at nominal full press. Three separate return disks are radius 0.7, free 1.1 mm, working 1.0 mm at rest and 0.4 mm at the face stop. Radius 0.9 face bosses cover their complete nominal 1.539 mm² area; alignment/shear still needs testing. Foam preload, nonlinear response, temperature, creep and repeated use are not simulated. [Rogers HT-800 data](https://www.rogerscorp.com/-/media/project/rogerscorp/documents/elastomeric-material-solutions/bisco/english/data-sheets/180-070-ht-800---medium-cellular-silicone.pdf) lists 0.79 mm availability and 41–97 kPa at 25% deflection. Applied to 38.44 mm², that is a **calculated**1.58–3.73 N, not an installed force measurement. The 6.3% rest preload must stay below the 0.9 N switch minimum; measured actuation must exceed 1.5 N before the chosen stop. The data does not establish either condition for this thin cut pad.

## Assembly and release gates

Use unpowered gauges first. Inspect the cup and thread; preseat acoustic working gaskets; insert the fork radially through its 6.4 × 1.3 mm assembly opening; lower the measured privacy keeper from the front; install contact carrier, sensor/interface/retainer, pack/growth/dielectric gauge stack, proposed board and carrier with its measured clamp/return pads. Assemble the window, foam, shoe and keeper separately in the face, using the two-leg keeper path, then lower the face over the guides. Seat the fixed diffuser in the bezel and rotate the bezel on the demonstrated helical path. The reverse sequence is the modeled service route. Free foam compression during assembly, flexible-wire dressing and real connectors remain physical process work.

The sensor cap rests atZ 4.2 and has 0.1 mm travel below the board. Integrated ducts have real Ø1.3 bores, but microphone port datum, gasket sealing, mesh and acoustic response remain proposals. The dock part is an insulating access carrier; selected mating contacts, nose, strain relief and powered dock qualification remain separate. The nonconductive champagne finish, light emission, RF environment, skin contact and bail/chain loads are not qualified by rendering.

Small geometry is deliberate trial stock: 0.30 mm shoe plate, 0.50 mm diameter carrier support arms, 0.60 mm ledges, thin optical features, rounded printed threads and 0.1–0.25 mm local clearances. These need same-process coupons, measured loads/deflection, strength and cycle testing; **topology pass does not make them a safe printable mechanism**. The original coupon does not qualify these new details. Thread torque, anti-loosening, sealing, off-axis face presses, switch/foam selection, complete native placement, supplier pack approval, RF/acoustic/thermal and worn-device testing remain release gates.

## Reproduce

With Blender 5.2 and Python available, run for both scenario IDs:

```powershell
blender -b -t 2 --python build_m2.py -- --scenario documented-pack
python verify_meshes.py --scenario documented-pack
blender -b -t 2 --python check_m2.py -- --scenario documented-pack
blender -b -t 2 --python render_m2.py -- --view assembled
blender -b -t 2 --python render_m2.py -- --view exploded
python engineering_audit.py
python package_m2.py
```

[Assembled inspection](documented-pack/m2-assembled.png) and [exploded inspection](documented-pack/m2-exploded.png) show the actual 43 × 12.2 mm primary source. Render scripts always set `visuallyInspected:false`. Only a separate review of the exact PNG, bound to its hash, can record inspection. [Readiness](readiness.json) checks current source/output hashes and preserves all non-digital release gates as false.
