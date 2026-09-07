# AURA A03 — capsule enclosure / prototype CAD

AURA is a compact note-taking pendant with a polished black recording face inside a satin silver capsule. Pressing the face actuates the PCB record switch; double press is the intended bookmark gesture. The right-side slider operates the microphone power disconnect. Two acoustic ports and a recording indicator sit in the black face. An integrated bail carries the optional fine chain.

**This is a printable mechanical prototype package, not a production release.** Closed meshes and nominal packaging checks are complete. Physical prints, moving-face feel, assembly tolerances, acoustic seals, thermal behavior, RF, battery fit/swelling and skin-contact materials remain unqualified. Internal GLB electronics are package-envelope proxies, not a routed PCB/STEP export. Refer to the hardware folder for electrical manufacturing status.

## Files

| File | Purpose |
|---|---|
| `build_aura.py` | Reproducible Blender geometry, manufacturing meshes, materials and renders. |
| `pcb-placement-reference.json` | Snapshot used to position internal package proxies. |
| `component-body-reference.json` | Source nominal package dimensions and individually verified maximum-body envelopes. |
| `hardware-placement-sync.json`, `placement-current-audit.json` | Final nine-component placement delta and focused package/cavity clearance assessment. |
| `print-invariance.json` | Baseline/current signatures that detect unintended changes to any of the eight print meshes. |
| `model-sync-audit.json` | Independent GLB transform checks for all 56 package proxies and dimension checks for 50 power/passive/diode bodies. |
| `aura-product.blend` | Editable assembled scene, with hidden FABRICATION collection. |
| `aura-front-shell.stl` | Open frame with face retention ledge, travel stops, slider opening and bosses. |
| `aura-rear-shell.stl` | Rear cup with bail, PCB shelves/clips, battery cavity and contact opening. |
| `aura-record-face.stl` | Whole-face paddle with integral plunger and four retaining tabs. |
| `aura-privacy-slider.stl` | Exterior slider only; internal switch coupling still requires engineering. |
| `aura-top-retainer.stl` | Nonconductive prototype press-fit retainer. |
| `aura-contact-carrier.stl` | Three-contact carrier with lead feedthroughs. |
| `aura-fit-coupon.stl` | Printer bore/slot calibration coupon. |
| `aura-dock-alignment-jig.stl` | Passive contact-alignment fixture; no charger electronics. |
| `aura-device.glb`, `aura-pendant.glb`, `aura-exploded.glb` | Device only, device with chain, exploded presentation. |
| `aura-mechanical-drawing.svg` | Dimensioned orthographic and stack drawing. |
| `PRINTING.md` | Print setup, fit checks, assembly and mechanical BOM. |
| `mesh-audit.json`, `assembly-audit.json` | Topology, contact alignment and solid-intersection reports. |
| `design-contract.json`, `asset-manifest.json` | Machine-readable interfaces and current artifacts. |
| `renders/` | Blender hero, detail, near-profile, rear and exploded plates. |

Earlier revisions under `archive/` are superseded. `archive/A02-working` was interrupted by the user-directed A03 revision and is not a completed design.

The current A03 internal model incorporates the final charger/comparator routing moves and the Q1 body-clearance correction. All eight printable STLs remain **byte-for-byte identical** to the pre-sync checkpoint. `print-invariance.json` records both file and triangle-geometry signatures. The ten-package focused audit reports no envelope overlaps, contacts or case/moving-face intersections; manufacturer maxima are used for the individually verified parts described in `PACKAGE-ENVELOPES.md`. These digital checks do not change the prototype's qualification status.

## Mechanical contract

Nominal units are millimetres. CAD axes: X width, Y height, Z depth; front is +Z. Blender geometry is metres; STL exports are millimetres. The small slider protrudes about 0.16 mm beyond the right side.

| Feature | Nominal contract |
|---|---|
| Main body | **28 W × 48 H × 10 D**, capsule R14 family |
| Including integrated bail | **28 W × 54 H × 10 D** |
| Inner capsule | 25.6 W ×45.6 H, R12.8; arc centers Y±10 |
| PCB | **24 W ×42 H ×0.8, R10 corners** |
| PCB bottom/top | Z−0.15 /+0.65 |
| PCB/capsule XY clearance | Minimum approximately 0.564 near rounded corners; clips approach edges intentionally |
| Black face paddle | 23.2 W ×43.2 H,0.9 skin; retaining tabs extend width to 24.65 |
| Face rest / travel | TopZ4.95, undersideZ4.05; target 0.35 inward travel; stop ceilingZ3.70 |
| Face aperture | 23.6 ×43.6;0.20 radial gap |
| Seam | Z±0.055,0.11 gap;0.08 gasket reference |
| Sidewalls / rear floor | 1.2 at straight sides /1.0 nominal floor; curved transitions vary |
| Protected-cell target | 150 mAh; candidate nominal 20 ×27 ×3 includes PCM length |
| Maximum modeled cell allowance | **20.5 W ×28 H ×3.3 D**, center(0,−3,−2.10); unqualified allowance |
| Cell bounds | X±10.25, Y−17..+11, Z−3.75..−0.45 |
| Cell/PCB and rear clearances | 0.30 above cell including 0.05 insulation;0.25 below cell |
| Antenna exclusion | Y>11.95 through upper PCB; no cell or conductive coating here |
| Haptic max envelope | C08-00A Ø8.1 ×2.75, center(+6,−12);0.05 insulating film underneath |
| Haptic Z / pressed-face clearance | Z0.70..3.45 /0.25 nominal |
| Record switch | SW2(0,−6), actuated by full-face integral plunger |
| LED | (0,−1), apertureØ0.62, lensØ0.50 |
| Acoustic ports | (−8.5,+8.5),(+8.5,+8.5), Ø0.70 |
| Privacy switch | SW1(+9.5,−0.2),90°; exterior atX≈14,Z1.4 |
| Three rear contacts | **X−3,0,+3; Y−19; Ø1.70**, exposed surfaceZ−5 |
| Carrier | 9.8 ×2.9 ×0.7; top edgeY−17.55,0.55 below cell |
| Retainer centerlines | (0,±22.5), beyond PCB ends±21 |
| Fastener interface | BossØ2.5, pilotØ0.96, rear clearanceØ1.36, head seatØ2.04 |
| Bail | Integrated rear polymer; transverseØ3.4 passage;6 mm above body |

The 10 mm depth preserves a 0.9 mm printable moving face, travel and the cell allowance. The depth budget does not include a qualified battery-swelling allowance.

## Functional mechanism and limitations

The black face enters from behind the frame. Four tabs capture it under the ledge; four wall-connected stops limit inward movement. A compressible perimeter return-gasket reference supports it. The plunger ends atZ2.57, about 0.02 above the switch actuator envelope atZ2.55. SW2 is KMR211NGULCLFS, nominal 1.2 N with operating travel 0.20±0.10; target available switch movement is 0.33. Actual switch operating travel/force, preload, face bending under off-axis presses, tab strength and return feel must be measured. Face movement must not load the RF module, motor or cell. The 0.35 mm travel is a design target, not a tested mechanism.

Bottom-port microphones need sealed paths from moving-face apertures to PCB underside holes. Dark Blender tubes show intended wrap-around routing, not printable hollow ducts. Compliant boots must accommodate face movement and avoid acoustic leakage, clothing noise and occlusion. The LED needs a compliant lightpipe interface. No ingress-protection rating is claimed.

The printed side slider is the exterior actuator. Its dog-leg/fork coupling to the DPDT switch remains unengineered against the final vendor actuator drawing. The amber marker identifies the intended off end. The external actuator STL is not a complete functional privacy mechanism.

J1 moved toY−19 in A03, below the cell. Short contact tails or a small passive interposer can reach the board without crossing the battery. Visible disks and carrier holes are mechanical references. Actual contacts, termination, insulation, travel and docking tolerances must be selected before power is applied. The dock STL is a passive jig, not an electrically complete charger.

Silver denotes a **nonconductive finish on polymer**; metallic shader parameters only depict its appearance. A metal shell, conductive coating over the antenna or metal top fastener needs a different RF design. The chain is a styling option requiring worn RF testing and a selected breakaway clasp; it is not an approved accessory. The top retainer remains polymer.

Cell width/thickness maxima and swelling behavior are not fully specified. The enlarged envelope is provisional. Physical qualification may require more space. Thermal behavior, charge temperature sensing and shutdown follow hardware review. Do not charge an unqualified cell inside a tightly closed print or wear uncured/unqualified resin against skin.

## Reproduction and Three.js integration

Blender 5.2.1 LTS is installed at `C:/Program Files/Blender Foundation/Blender 5.2/blender.exe`. Built-in Python, Cycles, STL and glTF exporters generate all assets; no add-ons are required.

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --threads 6 --python F:\circuit\enclosure\build_aura.py
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --threads 4 --python F:\circuit\enclosure\verify_geometry.py
```

Append `-- --no-render` for geometry only or `-- --preview` for a 1000px preview. The script clears the scene; run in a separate Blender process. Import STL at 100% and interpret units asmm.

glTF uses metres and maps CAD front+Z to glTF+Y; pendant top becomes glTF−Z. A wrapper rotation of+π/2 aroundX gives front+Z and top+Y for a conventional Three.js view. Mesh roots remain independent: `Housing_Front` is the silver frame, `Housing_Back` rear/bail, `Record_Button` entire black face, `Record_Plunger` visual stem, `Privacy_Slider` side control, and `Top_Polymer_Retainer` belongs to the rear group. `Chain_Left`/`Chain_Right` are optional chain segments. FABRICATION is excluded from GLBs. Internal packages use placement proxies; actual routes/pads and electrical release status are in hardware files.
