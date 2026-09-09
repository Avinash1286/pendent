# AURA A04 — circular industrial-design contract

**Status: proposed packaging contract, not a fit-qualified design or print release.** This revision follows the supplied circular pale-satin pendant reference. A03 remains a separate, unchanged capsule release. No A03 PCB, cell, switch linkage, acoustic boot, or printable part is assumed to fit A04.

## M2 development checkpoint — Ø43 mm front-loaded candidate

The separate [M2 mechanism](../../enclosure/a04/mechanism-m2/README.md) replaces M1's blocked rear insertion with an open-front cup and removable threaded polymer bezel. Three positive PCB supports and matching retained clamp feet establish the actual 1.6 mm board plane. A guided captive face has independent 0.6 mm face and 0.25 mm calibrated shoe stops, a measured foam cartridge, full-area return-pad bosses and local radio relief. The keeper follows a sampled two-leg subassembly path; the completed face loads from the front. M1 and the original study below remain preserved historical checkpoints.

M2 is **43 × 12.2 mm** in the primary documented 4.3 mm pack-depth render, or **43 × 11.2 mm** for the unselected 3.3 mm pack goal. Both use Ø35.2 × 1.6 mm PCB gauges and a 26 × 21 mm pack at (−3.2, 0), with the 0.4 mm growth allowance modeled as a solid. Neither pack is approved; 0.8 mm PCB thickness remains an unauthored target. The source files, 14 individual STLs per scenario, full XYZ/hash/topology audits and actual 43 × 12.2 assembled/exploded renders are in the M2 directory.

Both M2 digital scenarios pass the scoped all-solid checks: 54 rigid and 12 working soft allocations, 25 coupled capture poses, three privacy travel/width cases with 54 take-up samples each, and 16 insertion/subassembly/tool-access paths totaling 668 samples. These are finite CSG samples, not continuous motion, force or tolerance proof. All 72 native PCB features / 68 purchased PCB references remain pending; the current native board has zero placed components. Most package geometry, RF, supplier pack, physical prints, strength, actuator endpoints, material creep, acoustic/thermal and worn-device qualification remain release gates. In particular the 0.30 mm shoe plate and 0.50 mm support arms require physical structural/process work. M2 is **not a print or wearable release**.

**M1 privacy errata:** the [unassigned CUS candidate verification](cus22-candidate-verification.json) is authoritative. Correct source mapping is `CAD X=13.5+source Y; CAD Y=−source X`. The actuator centreline is nominal X 14.85, with full body/offset/actuator tolerance X 14.10..15.60 before locator/play. The old upper-right M1 notch clips an anchor by about 0.568 mm and is not retained. M2 models all signal pads, anchors and locator holes, plus conservative full lead fields. Its 2.0 mm fork gap uses a measured replacement keeper: nominal 4.4 mm channel gives 2.2 mm external stroke; preliminary component extremes require 4.1..4.7 mm channels. The native JS202 part is unchanged. Neither safe lever endpoints nor switch adoption follow from a modeled stop or footprint alone.

## M1 mechanism checkpoint — separate Ø41 mm proposal

The newer [M1 experiment](../../enclosure/a04/mechanism/README.md) now contains actual hollow housings, a captive face/flange and retainer, guide/stop features, separate diffuser/lightpipe, a privacy fork/keeper, acoustic ducts, contact access, sensor carrier and unpowered gauges. Each of its two scenarios exports **12 candidate parts plus 2 gauges**, with source Blender files, independent mesh checks, expanded motion checks and [an exploded inspection](../../enclosure/a04/mechanism/thin-cell/mechanism-exploded.png). It does not constitute a complete-body assembly or print release.

M1 proposes Ø41 mm while retaining the original Ø35.2 mm face, preserving the usefulness of the verified [process coupon](../../enclosure/a04/coupon/README.md). Both candidates use the **actual1.6 mm PCB thickness**: body depth10.8 mm for the controlled3.3 mm cell goal, and11.8 mm for a4.3 mm pack-depth scenario. The0.8 mm PCB remains an unauthored target. Guides, stops and return pockets share the radial annulus/existing component-height region; a full additional mechanism band was not added. The original Ø40 mm study and its hash-bound contract remain unchanged below.

The [M1 contract](../../enclosure/a04/mechanism/mechanism-contract.json) and [proposed XY map](../../enclosure/a04/mechanism/allocation-audit.json) move the controlled pack to(−1.9,−1.3), use different closure/column positions and examine an underside CUS-22TB DPDT at(13.5,0). That candidate's transformed nominal pad corners leave0.600 mm to the Ø35.2 board edge against the actual0.500 mm copper-edge rule. The native JS202011JCQN is **unchanged**; the original switch's nominal5.5 mm body-plus-actuator height conflicts with the thin generic top stack. Full CUS terminals, anchor-grounding requirements, native footprint and tolerances are not approved.

**The M1 checks expose unresolved failures:** the full face cannot slide axially from the rear past the integral closure bosses; a tilted or alternative construction is unproven. The PCB's axial plane lacks positive support and retention. At full0.4 mm press, the status lightpipe intersects the proposed radio maximum by about0.022 mm³ in both depth scenarios. The plunger sizing blank demands0.35 mm switch depression against a published0.1–0.3 mm electrical travel range, without safe-overtravel proof. Consequently both expanded motion reports remain false, despite all28 exported STL specimens passing topology/hash/XYZ checks. The0.190 mm left boss-to-pack gap is a small unqualified clearance, not a successful tolerance fit. No powered or wearable assembly is qualified.

The [M1 README](../../enclosure/a04/mechanism/README.md) records fastener/material evidence, proposed microphone/dock/NTC interfaces, insertion accessibility and the exact exclusions. The [readiness report](../../enclosure/a04/mechanism/mechanism-readiness.json) binds final checkpoint artifacts. The remainder of this document describes the **preserved original Ø40 mm appearance/packaging study**, whose coordinates and Blender metre convention must not be mixed with M1's millimetre-coordinate source.

The intended object is a 40 mm circular pendant with a quiet satin face, a fine champagne-looking rim, a stationary light ring, one small central status dash, and a short bail. The reference is visual direction only: it provides no dimensional, material, electrical, or acoustic specification. The entire face remains the deliberate record/stop gesture; the side privacy slide remains a separate physical control. Decorative side perforations from the reference are not copied as unexplained openings.

## Current board reality and the thickness target

The target is **Ø40 ×10.0 mm**, excluding a short bail and small privacy actuator. Less than 10 mm is an aspiration, not a committed specification. Root reports the new native KiCad board is currently Ø35.2 mm and four layers, but its actual board thickness remains **1.6 mm** because the available MCP operations have not exposed a working thickness setter. The mechanical target is 0.8 mm. Those are different values and must remain visible in every release check.

With the provisional stack below, 1.6 mm PCB thickness requires **10.8 mm body depth** to preserve the same clearances. The isolated preview therefore defaults to 10.8 mm, not a misleading 10 mm rendering of an overfilled case. If routing needs a Ø36–37 mm board, revisit retention, microphone channels, and wall clearance before changing the outline. No STL or final product render should be released from the current compartment preview.

The machine-readable assumptions are in [the A04 draft contract](../../enclosure/a04/design-contract.json). [The isolated Blender scaffold](../../enclosure/a04/build_aura_a04.py) only makes a packaging study; it does not import final populated-board geometry or generate printable parts.

## Parametric geometry and interfaces

CAD uses millimetres: X right, Y toward the bail, Z outward from the chest; front is +Z. Blender geometry is metres. With a board datum at native KiCad (100,100), the intended XY mapping is `kicad_x = 100 + cad_x`, `kicad_y = 100 − cad_y`. Root must verify the actual native origin and rotation before any package import.

| Parameter | Draft value or constraint |
|---|---|
| Body | Ø40.0; 10.0 target depth, 10.8 current 1.6 mm-board packaging preview |
| Body contour | Shallow front and back edge rolls; retain a broad flat rear contact area; no pointed coin edge |
| Main cavity | Ø37.6 nominal through the useful stack; 1.2 radial wall before local bosses/ducts |
| PCB | Ø35.2 initial target; 0.8 target / 1.6 actual reported thickness; outline notches unresolved |
| PCB edge clearance | 1.2 nominal radial at Ø35.2; 0.8 at Ø36; 0.3 at Ø37 before tolerances, clips, or channels |
| Face paddle | Ø35.2, 1.0 skin; opaque pale satin nonconductive material |
| Face aperture | Ø35.7; 0.25 nominal radial running gap before coating/process adjustment |
| Face stroke reservation | 0.40 inward target; final electrical actuation, rest gap, compliance and hard-stop stroke must be measured |
| Fixed diffuser | Inner radius17.85, outer18.55: 0.70 radial visible band; mechanical depth and extraction texture remain optical design work |
| Cosmetic rim | Remaining face perimeter, visually narrow through chamfer/highlight rather than an unrealistically thin structural wall |
| Status dash | 3.0 ×0.5 visible target at face centre; separate from the decorative ring's animation control |
| Bail | 5.2 width, 4.0 extension above body, 3.8 depth target; transverse Ø2.6 chain passage; final radii/load path unresolved |
| Overall height | 44 target excluding the chain and any selected separate jump ring |
| Closure | Two lower side screws plus upper polymer location key; rear removable without forcing the cell |
| Provisional screw bosses | Polar210° and330°, radius17.8: (−15.415,−8.9) and(+15.415,−8.9); Ø3.6 boss envelope |
| PCB notch negotiation | Reserve boss envelope plus ≥0.30 radial assembly allowance; exact Edge.Cuts and copper/lead clearance belong to native PCB review |
| Dock row | Rear centres X−3,0,+3 atY−15.5; Ø1.7 exposed contact target, with insulating carrier |
| Cell compartment | Maximum pack26.0 ×21.0 ×3.3, centreXY(0,−1.5), inclusive of PCM and folded-tab body envelope; separately route and restrain leads |
| RF allocation | Upper sectorY≥9.8 provisionally reserved across the case; exact all-layer copper keepout follows the selected module drawing/placement |
| Microphone allocation | Stationary lateral/lower-frame channels, outside the cell envelope; final port/PCB-hole coordinates deliberately not frozen |
| Privacy control | Right side, recessed external tab; positive mechanical end stops and direct internal coupling to the selected disconnect switch |

At cell centre(0,−1.5), the lower corners of a26×21 maximum rectangular pack reach radius `sqrt(13² +12²) =17.692 mm`, leaving1.108 mm to the nominal Ø37.6 cavity. This is a simple envelope calculation, not a swelling, curvature, lead, fastener, or print-tolerance result. The old A03 allowance, rotated to28×20.5 at the same centre, reaches18.278 mm and leaves only0.522 mm before those effects. Its original orientation extends into the provisional RF sector. A04 therefore needs a controlled supplier drawing rather than a relabelled A03 battery box.

## Depth budget

The following is an allocation at the 0.8 mm board target. Z−5 is the rear exterior; Z+5 is the outermost front datum. “Maximum” below means the envelope the design can accept; it is not a verified property of an unselected part.

| Layer, rear to front | Allocation | Target Z range |
|---|---:|---:|
| Rear skin |1.00|−5.00..−4.00|
| Cell backing/fixation |0.15|−4.00..−3.85|
| Supplier maximum pack thickness |3.30|−3.85..−0.55|
| Provisional cell-growth space |0.40|−0.55..−0.15|
| Dielectric plus free separation |0.15|−0.15..0.00|
| PCB target |0.80|0.00..0.80|
| Component plus solder/mount maximum |2.45|0.80..3.25|
| Clearance to fully pressed face |0.30|3.25..3.55|
| Face travel reservation |0.40|3.55..3.95|
| Face skin |1.00|3.95..4.95|
| Cosmetic setback to rim datum |0.05|4.95..5.00|
| **Total** |**10.00**| |

The 0.40 mm battery-growth allocation is an engineering placeholder, **not** a supplier-approved swelling limit. The battery supplier's maximum charged/end-of-life envelope, tab bend limits, protection board, insulation, attachment and thermal sensor must determine the real compartment. Do not use the cell as a spacer, structural support, or clamp surface. If the qualified envelope exceeds the budget, increase thickness or select a different pack; do not consume the moving-face or electrical isolation space.

**Temperature-sensor accommodation is still open.** Hardware screening gives the existing Semitec103AT-2 a maximum4.0×3.7×2.4 mm body, so it cannot simply be bonded on top of a3 mm pouch inside a3.3 mm pack allocation. Reserve a tentative cell-edge contact pocket, not an unexplained overlap: a5.0×4.5×3.0 mm region centred nearXY(15.5,1.75), alongside the pack, is a packaging candidate. Its inner X boundary is13 mm, at the maximum pack edge; it still needs an insulating carrier, adhesive/contact thickness, lead restraint and exact shell/PCB/duct collision checks. Edge contact does not prove adequate temperature tracking or shutdown margin. A thinner sensor would require its own R/T and circuit qualification. Neither the pocket nor the sensor is an approved battery assembly. [Semitec AT drawing/specifications](https://www.semitec-global.com/uploads/2022/01/P12-13-AT-Thermistor.pdf); [existing thermal qualification contract](../thermal-review.md).

The retained Raytac MDBT50Q-1MV2 is nominally10.5×15.5×2.05 mm; Version L page7 applies a+0.20 mm maximum tolerance, giving a10.7×15.7×2.25 mm body envelope. The study reserves another0.15 mm for solder/seating, leaving0.05 mm within the2.45 mm component allocation; the actual installed height/warpage still needs measurement. The A03 C08-00A haptic allowance was2.75 mm before mounting, so it does **not** fit this straight stack. [Raytac Version L drawing, reviewed manufacturer PDF mirror](https://www.espruino.com/datasheets/MDBT50Q-1M.pdf#page=7); [manufacturer product/specification entry](https://www.raytac.com/product/ins.php?index_id=24); [A03 package/qualification limits](../../enclosure/MECHANICAL.md).

The preferred thin-motor candidate from hardware review is **Vybronics VCLP1020B002L**, a brushed ERM. Its drawing specifiesØ10±0.1 and2.1±0.1 mm body, plus0.15 mm tape:2.35 mm before any tape/mounting tolerance. Keep the2.45 mm mounted allowance, the tab extending6.6 mm from centre, and a protected route for the25±1 mm leads. This is an engineering candidate, not a qualified haptic assembly or a drop-in LRA firmware setting. Its operating/startup current, drive mode, mounting, feedback feel and the manufacturer's caution about adjacent magnets must be checked; use a nonmagnetic keyed dock initially. A PCB recess is a separate structural/routing redesign. Capacity, runtime, haptic strength and the final charge setting remain uncommitted. [Vybronics drawing, PDF page12](https://www.vybronics.com/wp-content/uploads/datasheet-files/Vybronics-VCLP1020B002L-datasheet.pdf#page=12).

## Face, light and privacy mechanism

The ring belongs to the fixed frame. The pale face is captured from behind by a replaceable guide/retainer with at least three distributed bearing locations and a compliant return element. A selected tactile switch receives force through a guided or locally compliant plunger. The plunger must be adjustable in prototype increments or finish-machined after measurement; an uncalibrated resin print is not a reliable0.02 mm switch gap. Structural hard stops transfer excessive face load to the housing, not to the switch, PCB components, radio shield, or cell.

For the existing KMR211 family, published electrical travel is0.20±0.10 mm and nominal actuator height is1.9 mm. Those values alone do not specify a safe complete face mechanism. Check actuation before the minimum assembled stop position, release at rest, permissible overtravel and side load with the exact ordered part. The0.40 mm reservation is intended to leave room for that tolerance work, not a claim that every KMR211/printed-plunger combination is safe. Off-centre presses on a35 mm face need measured stiffness and return tests. [C&K/Littelfuse KMR2 datasheet](https://www.ckswitches.com/media/1479/kmr2.pdf).

The central dash is the unambiguous recording/microphone-power indication. It should remain tied to the physical microphone power state rather than depend solely on app or animation state. Its lightpipe travels with the face and needs a compliant optical interface and opaque separator. The stationary ring is a separate lightguide, with emitters and conductors kept outside the RF sector; brightness uniformity and power budget require an optical prototype. Do not depict a uniformly glowing, low-power ring as achieved merely because Blender uses an emissive material. No always-on ring is assumed.

Use a physical privacy slider with tactile end stops and a visible off marker. The external actuator must have an actual fork/linkage that accommodates the switch's travel and tolerance without overloading its lever. The A03 external-only slider is insufficient. Opening the microphone supply must prevent capture and extinguish the hardware indicator in all firmware states, including fault/reset; the MCU may report the switch state but cannot override it. The final pin-to-position truth table belongs to the schematic and first-article measurements.

## Antenna, acoustics and dock

**RF:** retain a nonconductive structural shell, face, diffuser and upper bail in the first prototype. The champagne highlight is a visual finish target; a continuous metal ring, metallized paint, metal fastener, chain, or battery foil near the antenna changes the RF problem. Reserve the whole upper sector while hardware chooses the module position, then apply the exact Raytac all-layer antenna keepout and measure the assembled, worn device. The provisionalY≥9.8 sector is not a substitute for the module specification. Test with and without the intended chain and against the body, in realistic orientations. A decorative metal rim must not be approved by appearance alone. [Raytac specification/footprint design-guide entry](https://www.raytac.com/product/ins.php?index_id=24).

**Acoustics:** use two stationary exterior ports, preferably on the fixed lower/lateral frame so neither channel crosses the moving face. Reserve a separate compliant sealed boot for each microphone, a real PCB acoustic opening, and space outside the cell for the underside channel if using bottom-port MEMS. Do not represent solid Blender tubes as hollow printable acoustic ducts. The current Knowles part is a bottom-port PDM microphone; the maximum package and its port datum must be taken from its controlled drawing before placing nearby packages. A03's MK2/U7 maximum-body conflict is a known reason to redo placement, not copy it. Avoid sharing cavities between microphones, routing through a gasket compression seam, or placing openings against clothing without testing. Ports, hydrophobic mesh and seals need transfer-response, rub/wind, sweat and occlusion checks. No speaker or water-resistance rating is inferred from the reference perforations. [Knowles product description](https://investor.knowles.com/news/news-details/2014/Knowles-Enables-Touch-less-Gesture-Recognition-for-Smartphones-and-Tablets-06-17-2014/default.aspx); [A03 maximum-body finding](../research/omi-hardware-review.md).

**Dock:** preserve a keyed three-contact arrangement with guarded polarity and current-limited supply, but select actual rated contact hardware, stroke, mating height and attachment before powering it. Keep the carrier and lead route below the cell; the target row atY−15.5 has space for a short carrier without crossing the pack. The dock must constrain XY/rotation mechanically rather than relying on pogo friction. A keyed recess is preferred initially; magnets are optional engineering parts, not present by default. An insulating printable alignment fixture remains an unpowered fit aid until dock circuitry, contacts, reverse/misalignment protection, retention, contact resistance, contamination and thermal behavior are verified.

## Printing and assembly tolerance contract

Initial mechanical prototypes should use a dimensionally controlled tough polymer process and fully finished surfaces; the material/process choice is not yet skin-contact qualified. The case walls target1.2 mm, rear1.0 mm, and face1.0 mm. Retention features should start at ≥0.6 mm thickness rather than reusing A03's0.3 mm clip lips. Exact minimums depend on selected material and orientation. Use screws or replaceable retainers where a failed brittle snap would make the case unusable.

The independent [nine-specimen face/rim process coupon](../../enclosure/a04/coupon/README.md) now supplies full-size35.2 mm mating geometry with0.15/0.20/0.25/0.30 mm radial gaps, wall specimens, and a transverse bail-hole/relative-pin trial. Its checked STLs are for unpowered process trials, not complete A04 case parts. Physical measurements remain blank.

Treat0.25 mm radial face clearance and0.30 mm boss/board clearance as initial design allowances, not printer accuracy. Budget geometry, placement, post-cure distortion, coating on both mating faces, gasket compression and temperature separately. Never apply global STL scaling to repair one undersized bore. Make a same-process coupon containing the face running gap, carrier fit, selected screw pilot/clearance, bail hole, and actual microphone/light apertures. Ordinary0.4 mm-nozzle FDM may be useful for a coarse fit shell/dock, but cannot be presumed to resolve the optical/acoustic and moving-face features.

Keep the rear removable for inspection and battery replacement; the battery should lift out without levering against the pouch. Assembly order should be: measured empty shell and face mechanism; unpowered dummy board/pack fit; qualified fixed contacts and privacy linkage; acoustic/light interfaces; board and insulated qualified pack; controlled closure. Final screws must not enter the pack or acoustic channels. Their exact diameter, under-head length, thread engagement, torque, and head-seat profile remain open until selected hardware is modelled.

## Required checks before each release stage

| Gate | Required evidence |
|---|---|
| Interface freeze | Native board diameter/notches, actual0.8-or1.6 thickness, origin, mounting keepouts, controlled supplier cell drawing, exact radio/mic/switch/haptic/contact drawings and power budget accepted together. |
| Mechanical digital fit | Actual maximum body/lead envelopes, solder allowances, placement tolerance and native courtyard review; no hidden exception for MK2/U7 or a same-net pad overlap. Sweep the fully pressed face, privacy linkage, insertion path, fasteners, wire bends and swollen-cell envelope against real solids. |
| Parametric checks | Verify every layer sum, min wall/floor, boss-to-cell distance, board-edge/notch gap, RF exclusion, dock polarity datum and unit/orientation mapping. Fail the10 mm claim if actual board/pack dimensions require more depth. |
| Print-kit release | Watertight positively oriented meshes, no unintended islands/self-intersections, minimum feature checks, explicit millimetres, dimension drawing and bill of materials. Export from the actual assembly geometry, with model/source/hash provenance and no A03 relabelling. |
| Empty physical assembly | Fully cured coupon dimensions, flatness, off-axis face actuation/release, repeated stroke/retainer wear, slider stop/linkage fit, dock/contact alignment and measured screw/bail retention. Use a dummy cell first. |
| Powered bench | Native electrical checks plus inspected assembly, current-limited power, measured privacy disconnection/indicator truth, audio channel integrity, local recording/recovery, charging-temperature/voltage/fault limits, storage and haptic validation with selected parts. Keep disabled functions disabled until their gates pass. |
| RF/acoustic/thermal | Assembled and worn radio performance with chosen finish/chain, audio with boots/mesh/clothing/wind, measured sound/handling noise, charge and workload thermal behavior, sensor attachment/lag and pack growth clearance. |
| Wear/launch | Qualified skin-contact finish, sweat/contact corrosion/insulation, drop and repeated docking, chain/bail and chosen breakaway behavior, usable privacy indication and complete user instructions. Manufacturer/certification review determines applicable compliance; neither CAD nor a clean DRC proves readiness to sell. |

A04 remains a design prototype until the relevant gate has evidence. Website, film, firmware descriptions and print instructions must use the actual selected dimensions and status. The current isolated model deliberately shows packaging allocations; it must not be presented as a routed PCB, qualified cell, printable functional mechanism, or completed launch product.
