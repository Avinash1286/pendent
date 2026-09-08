# A04 face/rim process coupon

Nine separate **unpowered test specimens**, not a complete pendant or production enclosure. They are independent of the unfinished A04 PCB. Physical fit, material strength, process accuracy and wear suitability remain unqualified. [Download the coupon kit](a04-process-coupon.zip).

The four rings test the actual proposed **35.2 mm face diameter**, so face-scale distortion and finishing effects are visible. The mating face gauge is shared between them. Do not scale any STL: files use **millimetres at100%**.

| Mark | STL | Working feature |
|---|---|---|
| R15 |[a04-face-ring-r15.stl](a04-face-ring-r15.stl)|35.50 bore;0.15 nominal radial gap to the35.20 face|
| R20 |[a04-face-ring-r20.stl](a04-face-ring-r20.stl)|35.60 bore;0.20 radial gap|
| R25 |[a04-face-ring-r25.stl](a04-face-ring-r25.stl)|35.70 bore;0.25 radial gap|
| R30 |[a04-face-ring-r30.stl](a04-face-ring-r30.stl)|35.80 bore;0.30 radial gap|
| F352 |[a04-face-gauge-35p2.stl](a04-face-gauge-35p2.stl)|35.20 working face,1.0 skin;37.20 retaining flange and rear grip|
|10 /12 /15 /B26|[a04-wall-bail-card.stl](a04-wall-bail-card.stl)|1.0 /1.2 /1.5 wall thickness,8 exposed height; transverse2.60 bail hole|
| P24 |[a04-relative-pin-24.stl](a04-relative-pin-24.stl)|2.40 shaft;0.10 nominal radial clearance in B26|
| P25 |[a04-relative-pin-25.stl](a04-relative-pin-25.stl)|2.50 shaft;0.05 radial clearance in B26|
| P26 |[a04-relative-pin-26.stl](a04-relative-pin-26.stl)|2.60 shaft;nominal line-to-line fit, not a forced-fit instruction|

Ring axial thickness is1.2 mm, outer diameter40 mm, and the identifying tab is outside the working bore. The face flange is an experimental stop, not a production retention feature. Insert the face from the **unmarked underside** of a ring; hold the rear grip, with the marked ring side facing out. The flange stays behind the ring. There is no spring, electrical switch, calibrated actuation force or travel stop.

B26 uses the actual proposed2.6 mm transverse passage through a5.2 mm-wide block. The cross-section is3.8 mm deep around the hole, giving0.6 mm nominal top ligament. It tests the hard-to-print transverse opening and thin surrounding material; the card base means it does not reproduce the bail's complete load path. The three printed pins are **relative-fit probes, not calibrated gauge pins**. Their rounded lead-in is excluded from shaft measurement.

## Use the intended print and finish process

1. Print the specimens with the same material, layer setup, orientation class, supports, wash/cure and finish intended for the final face/frame. Keep supports off running edges, bores and measuring faces. The files are placed atZ0 for inspection; this is not a requirement to print directly on the build plate. A direct-bed first-layer expansion can dominate these clearances.
2. Measure at least two perpendicular face/bore directions after full processing; record ovality and face/ring flatness. Measure wall thickness above the base, the pin shaft away from its tapered tip, and B26 using suitable measured gauges. Record instrument uncertainty. A snug fit between two equally shrunken parts does not establish absolute dimensions.
3. Try F352 in each ring without forcing or flexing it. Rotate it90° and180° and repeat. Record sliding, stick/slip, rub marks and any rocking. Compare supported and lightly handled rings so hand pressure is not mistaken for correct fit. Keep each ring's identity through finishing.
4. Repeat after the actual cosmetic coating. Coating on the bore and face edge both consume radial clearance: `finished gap ≈ printed gap − bore coating thickness − face-edge coating thickness`. Record measurements before and after, rather than adopting the smallest ring that can be forced together.
5. Compare the three wall specimens for measured thickness, distortion and handling damage. Compare B26 with measured P24/P25/P26 shafts or calibrated gauges; inspect the thin top ligament and print direction. These trials cannot qualify drop/chain loads or long-term fatigue.
6. Choose a process compensation only after repeated specimens give consistent results. Adjust the relevant parameter, not global scaling. The final device still needs its own moving-face, return-gasket, stop, slider, sealing, retention and worn-use tests after its geometry is frozen.

[measurement-template.csv](measurement-template.csv) is intentionally blank. It does not contain simulated physical results.

## Source and digital checks

From this directory:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --python build_coupon.py
python verify_coupon.py
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --python render_coupon.py
python package_coupon.py
```

[build_coupon.py](build_coupon.py) creates the solids and embossed marks using Blender, exports individual millimetre STLs, and saves [a04-coupon-layout.blend](a04-coupon-layout.blend) for inspection. [verify_coupon.py](verify_coupon.py) independently reads the actual binary STLs using Python's standard library. It checks file length/hash, closed consistently wound single-solid topology, positive volume and exported working diameters/wall thicknesses. Pin dimensions are measured at the straight working shaft by triangle-plane intersection, not at the tapered lead-in. These are meaningful export checks, not printer-fit results or a comprehensive self-intersection guarantee.

[coupon-manifest.json](coupon-manifest.json) binds the nine exports to their source; [coupon-mesh-audit.json](coupon-mesh-audit.json) records measured exported geometry. [render_coupon.py](render_coupon.py) imports those exact STLs for the overview. No A03 artifacts, PCB files or complete A04 body parts are altered by this kit.
