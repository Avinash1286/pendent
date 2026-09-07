# AURA A01 — industrial design and mechanical prototype

AURA is a discreet, screen-free note-taking pendant. A shallow circular record key is easy to find by touch, an illuminated pinhole communicates recording, two separated acoustic ports admit speech, and a recessed physical privacy slider provides a clear off position. A detachable black cord passes through a reinforced eyelet. The flat rear face is comfortable against clothing and has four recessed charging contacts.

This folder contains a real Blender model, procedural CAD-style source, hollow shell meshes, assembly visualization, and rendered product images. **It is a prototype design package, not a production release.** The internal reference parts are packaging envelopes; they do not replace the PCB team's electrical/manufacturing exports. Acoustic performance, assembly, RF, battery swelling, thermal behavior, cosmetics, and material suitability need physical verification.

## Files and reproduction

| File | Purpose |
|---|---|
| `build_aura.py` | Editable and reproducible Blender Python; every main dimension is expressed in millimetres. |
| `aura-product.blend` | Compressed editable assembled product, materials, lights, camera, reference electronics. |
| `aura-front-shell.stl` | Closed hollow front shell with acoustic/LED/button/slider openings and two screw bosses. |
| `aura-rear-shell.stl` | Closed hollow rear shell with eyelet, battery cavity, case fasteners, PCB support shelves and retaining clips. |
| `aura-record-button.stl` | Separate button cap. Silicone diaphragm and plunger must be engineered as separate production parts. |
| `aura-device.glb` | Assembled product without cord; recommended for interactive Three.js display. |
| `aura-pendant.glb` | Assembled product with two cord strands. |
| `aura-exploded.glb` | Exploded presentation with reference electronics. |
| `mesh-audit.json` | Automatically computed manifold-edge and volume report for the fabricated meshes. |
| `verify_geometry.py` / `assembly-audit.json` | Independent saved-scene topology and nominal solid-intersection checks. |
| `aura-mechanical-drawing.svg` | Dimensioned front, packaging and stack-section reference drawing. |
| `renders/hero-transparent.png` | Transparent product hero, 2000 × 2000. |
| `renders/hero.png` | Dark studio beauty, 2400 × 1600. |
| `renders/detail.png` | Right-side privacy slider/record button macro, 2000 × 1600, transparent. |
| `renders/rear.png` | Rear, charging contacts and markings, 2000 × 2000, transparent. |
| `renders/exploded.png` | Assembly concept, 2200 × 1800, transparent. |

Blender 5.2.1 LTS is installed at `C:/Program Files/Blender Foundation/Blender 5.2/blender.exe`. No add-ons are needed. Blender's bundled Python, Cycles, STL exporter and glTF exporter create this entire package.

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --threads 6 --python F:\circuit\enclosure\build_aura.py
```

Append `-- --no-render` for geometry/GLB/STL only, or `-- --preview` for a quick 1000px lighting preview. The script clears its Blender scene; run it in a separate Blender process as above.

## Mechanical contract

All dimensions below are nominal millimetres. Coordinates are X = left/right, Y = bottom/top, Z = rear/front. The outer body is centered at the origin.

| Feature | Dimension / position |
|---|---|
| Main body | 30 W × 40 H × 12 D; rounded perimeter, approximately R8 corners |
| Case including integrated eyelet | 30 W × 45.5 H × 12 D |
| Cord | Nominal Ø1.58; use a separate breakaway clasp for a wearable neck cord |
| Front shell | Z +0.18 to +6.00; approximately 1.2 side walls, 1.3 front wall |
| Rear shell | Z −6.00 to −0.18, with retaining clips extending to +2.4 |
| Shell seam | 0.36 gap occupied by a 0.32 silicone gasket reference |
| PCB envelope | 24 W × 34 H × 0.8, corner radius 4; center Z +1.55 |
| PCB underside / top | Z +1.15 / +1.95 |
| Tallest populated part | 2.1 above PCB; nominal maximum Z +4.05 |
| Haptic actuator exception | Off-board Ø8 × 3 LRA at (+6, −12); 0.05 insulation underneath, nominal Z +2.00 to +5.00 |
| Local haptic cavity | Ø8.5 front inner-ceiling recess to Z +5.10; 0.90 local front wall, 0.10 nominal motor ceiling gap |
| Front inner ceiling | Z +4.70; nominal tallest-component clearance 0.65 |
| Protected LiPo target | 20 W × 25 H × 5 D, center (0, −4, −1.9); 250 mAh is a sourcing target |
| Cell envelope | X ±10, Y −16.5 to +8.5, Z −4.4 to +0.6 |
| Cell–PCB nominal gap | 0.55, partly occupied by 0.05 insulation film |
| Cell–rear nominal gap | 0.40 at rear floor; selected cell swelling allowance still needs validation |
| RF exclusion | No cell or conductive coating behind upper antenna region, nominal Y +13 to +17 |
| Record key | Center (0, −6); cap Ø7.92; aperture Ø8.60 |
| Recording indicator | Center (0, −1); aperture Ø0.84, light pipe Ø0.68 |
| Dual acoustic ports | Centers (−8.5, +8.5) and (+8.5, +8.5); exterior Ø0.92 |
| Privacy slider | Right side, approximately X +15; Y=0; front half Z≈+1.65 |
| Four charging contact centers | X −3, −1, +1, +3; Y −14.4, rear face |
| Screw centerlines | (0, +18.4), (0, −18.4); outside PCB ends |
| Screw bosses | Outer Ø2.5; front pilot Ø0.96; rear clearance Ø1.36; counterbore Ø2.04 |
| Clip assembly | Four supports at X≈±12, Y −6/+5; underside rests at Z+1.15; clip lip underside at Z+2.10 |

The model intentionally has a flatter rear surface and gently domed front. The eyelet is part of the rear shell, so there is no exposed metal bail in the antenna region. Side details add less than 0.5mm to the nominal 30mm body width on the actuator side.

## Assembly and fabrication assumptions

1. Prototype shells in a dimensionally stable, skin-contact-appropriate polymer. A satin, nonconductive ceramic-effect finish communicates the moonstone/titanium aesthetic without putting a conductive shell over the antenna. The render's metallic appearance is a cosmetic direction, not a specification for a metal housing or conductive PVD coating.
2. Install the rear charging-contact carrier, insulated protected cell and soft battery locators. Do not compress, pierce, or bend the cell. The refined stack provides 0.4mm rear clearance and 0.5mm free space above the insulation. Confirm that allowance against the selected cell datasheet; a thinner cell or deeper rear shell may still be necessary.
3. Insert the populated PCB into the four rear support shelves. Four small lips retain it with 0.15mm nominal vertical free space. Prototype clip flex, insertion force and printed fit; injection molding would require draft, root radii and tool-direction review.
4. Install a real molded silicone acoustic gasket. Because the selected microphones are bottom-ported, the concept routes sound from the front apertures, around the board edge, to the board's underside acoustic holes. The dark tubes in Blender show intended routing only; they are not printable hollow ducts or a validated acoustic design. Design a leak-free gasket around the final PCB CAD and test clothing rub, wind, voice capture and port contamination.
5. Place the Ø8×3 coin LRA in the dedicated (+6,−12) region, on a 0.05mm insulating carrier. The hardware placement reserves an 8.5×8.5mm square free of populated components. Its special front-ceiling pocket provides only 0.10mm nominal clearance and a 0.90mm local wall: test this fit, tolerance stack, vibration coupling and thermal movement before committing parts or tooling. The rest of the front wall is 1.30mm nominal. The generic rectangular haptic placeholder has been replaced by the correct coin envelope.
6. Install the LED light pipe, sealed button diaphragm/plunger and privacy-switch actuator. The switch mechanically removes microphone power in the electrical design. The final board slider body is centered near(9.5,−0.2), rotated90°, while the external control is atX≈15; it requires a molded dog-leg linkage and a travel/clearance study. The visible external control is modeled, but that production linkage remains an engineering task. Confirm travel and alignment against the actual switches; cap travel, return force and tactile feel have not been simulated.
7. Seat the 0.32mm seam gasket and close the shell with two prototype M1.2 fasteners. Select the exact screw after checking head diameter against the 2.04mm counterbore and measuring usable pilot engagement. The rendered heads are visual references; no screw standard is implied. Ream/tune printed pilot holes rather than forcing a screw. Case bosses approach the PCB end with about 0.15mm nominal clearance, so this area needs explicit tolerance checking.
8. Fit a detachable, washable neck cord with a breakaway clasp. The cord in the beauty model is a presentation segment, not a complete clasp or a tensile-tested strap.

Suggested first fit coupon: print the PCB clips, 0.96mm screw pilot, counterbore, 0.84mm light-pipe hole and 8.60mm button aperture before printing both complete shells. Start with ±0.15mm polymer prototype dimensional capability and adjust features from measurements. Do not interpret that suggestion as a demonstrated process tolerance.

There is no IP rating, drop rating, battery-life claim, skin-contact certification, RF certification, ingress certification, or production qualification in this design. Charging/current limits and cell protection belong to the hardware and firmware verification plan. A revised mechanical stack is required if the chosen protected battery exceeds its target envelope.

## Three.js integration

glTF is in **metres**. A30mm-wide body is0.030 units. The source mesh has +Z toward the face and +Y toward the eyelet; Blender's glTF exporter converts Blender Z-up coordinates into glTF Y-up. Therefore, in the exported GLB the device front points **+Y**, pendant top points **−Z**, and width remains X. For a conventional front-facing display, wrap the loaded root in a group with `rotation.x = Math.PI / 2` (front then points +Z and pendant top +Y). The source CAD coordinates described above remain unchanged in Blender.

Named primary meshes: `Housing_Front`, `Housing_Back`, `Record_Button`, `Privacy_Slider`, `Seam_Gasket`, `LED_Lightpipe`, `PCB_Reference`, `Battery_Envelope`, `RF_Module_Envelope`, `Charging_Contact_1` through `Charging_Contact_4`, `Cord_Woven_Left`, `Cord_Woven_Right`.

For finish selection, clone the materials of `Housing_Front`, `Housing_Back`, `Record_Button`, and `Privacy_Slider` before recoloring; their default materials are intentionally shared by reference parts. For an exploded interaction, translate front parts +20mm along source Z, rear parts −22mm, and the battery −12mm. In an unrotated glTF model this means front +20mm along glTF Y, rear −22mm along Y, battery −12mm along Y. The pre-exploded GLB includes these translations.

The GLB includes part-name and design-status custom properties. It contains no embedded fonts, external textures, network calls or runtime dependencies. The cloth bump shader used in Cycles does not export to glTF; the glTF cord is plain rough charcoal.

## Verification scope

The generator computes non-manifold edge counts and signed closed volume for each exported shell and the record cap. All three must show **0 non-manifold edges** and positive volume in `mesh-audit.json`. This establishes closed mesh topology only. It does not establish minimum wall thickness everywhere, absence of every part collision, manufacturability, acoustic sealing, electrical safety, or mechanical reliability. The front/back/PCB/cell stack clearances above were checked against the explicitly agreed nominal envelope.

The independent saved-file audit passed: front shell, rear shell and record cap are each one connected component with zero non-manifold edges. All nine tested solid intersections are 0mm³: front/back; PCB/rear; PCB/front; battery/rear; battery/PCB; RF module/front; record cap/front; haptic/front; haptic/PCB. See `assembly-audit.json`. The verifier recalculates copied mesh normals and performs Manifold booleans at millimetre scale to avoid numerical instability in Boolean kernels on metre-scale wearable details. These are checks of selected nominal envelopes, not a complete tolerance or interference analysis of every electronic part.

Reference documentation: [Blender Python API](https://docs.blender.org/api/current/), [Blender glTF2 exporter manual](https://docs.blender.org/manual/en/latest/addons/import_export/scene_gltf2.html). This package uses the installed Blender5.2 exporter APIs directly.


