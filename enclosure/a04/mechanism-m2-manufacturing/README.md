# M2 S1 steel development drawings and cutting profiles

**For development quoting and unpowered fixtures only. No fabrication, strength, native PCB fit or wearable release.** These artifacts are derived from the two actual frozen S1 steel meshes. They do not revise the enclosure or substitute new geometry.

The two-sheet `m2-s1-steel-development-drawings.pdf` shows top and edge views, nominal dimensions, material/process notes and hashes. The separate `m2-s1-shoe-profile.dxf` and `m2-s1-lower-support-profile.dxf` are 1:1 millimetre cutting profiles. Matching SVGs provide a simple 1:1 visual profile. The PDF is an 8:1 view at A4 / 100%; dimensions are nominal and the mesh-derived DXF controls the contour. Do not scale a print to create toolpaths.

| Form | Mesh thickness reference | Defined actual incoming metal acceptance | Exterior profile |
|---|---:|---:|---|
| 08 metal plunger shoe | 0.300 mm | 0.28-0.32 mm | 9.000 x 6.200 mm rectangle, 4 vertices |
| 13 lower steel support | 1.000 mm | 0.95-1.00 mm | 12.174617 x 12.864318 mm envelope, 71 vertices |

These thickness values concern the separate steel, before adhesive and insulation. Preserve the minimum finished metal thickness and net CAD section after processing. Numerical extraction/round-trip tolerances in the verifier are computational checks, not approved manufacturing tolerances.

## Profile coordinates and exact source correspondence

Each DXF has one closed R2000 `LWPOLYLINE`, no holes, no extra construction entities, and `$INSUNITS=4` / `$MEASUREMENT=1`. The coordinates use a lower-left XY envelope origin, which is not a physical machined datum. CAD +Y is up, viewed from +Z. Restore assembly coordinates with `CAD XY = profile XY + origin`:

- Shoe origin: (-11.500000, -7.600000) mm.
- Support origin: (-15.074617, -14.264318) mm.

SVG Y is reflected for normal screen display; the DXF coordinate system is unchanged. The 71-vertex support includes the frozen mesh's faceted root curve. No new radius, smoothing, corner relief, kerf offset or geometric compensation has been applied. Quote any proposed contour/edge change for engineering review before manufacture.

`extract_profiles.py` reads the original BLEND files without saving them. It matches the two selected world-geometry hashes to each source manifest, extracts actual top-cap boundary edges, confirms a single closed boundary and two-plane extrusion, compares top and bottom profiles, checks volume against area times thickness, and independently compares the exported STL cap after its recorded transformation. It also verifies that both depth variants share the same XY forms. Full coordinates and source hashes are in `profiles.json`.

`manufacturing-verification.json` records independent ezdxf 1.4.4 reading without recovery, zero audit fixes/errors, one closed polyline per file, no self-intersections, area agreement and vertex round-trip error below 0.000001 mm. The PDF has two A4 landscape pages, required text and an explicit visual review of both final Poppler renders. It binds all supplied outputs plus their frozen source files. This proves digital correspondence only.

## Material, processing and interfaces

The candidate is cold-rolled ASTM A666 Type 301 / UNS S30100 half-hard, explicitly ordered and lot-certified for 0.2% yield at least 110 ksi / 758 MPa. A temper/hardness description alone is insufficient: the manufacturer's standard production guarantee can be tensile strength, yield or hardness. The listed 0.02-1.57 mm strip capability encompasses both thicknesses but is not a verified stock lot, width, MOQ or supply commitment. See [Elgiloy 301 material data](https://www.elgiloy.com/wp-content/uploads/2024/06/301-Alloy-Stainless-Steel-Data-Sheet-06042024.pdf) and [strip capability](https://www.elgiloy.com/wp-content/uploads/2024/05/ESM-Stainless-Strip-LineCard-DIGITAL-5.30.2024-compressed-1.pdf).

Preserve the supplied cold-worked temper. Controlled cold blanking or cool machining/deburring are proposed engineering process choices, without universal approved tool settings. No anneal, weld or hot straightening is credited without requalification; laser/EDM edges require finished-edge/property qualification. Parent-stock certification does not establish heat-affected edge properties. [Ulbrich discusses loss of cold-work strength with annealing](https://www.ulbrich.com/blog/understanding-the-difference-between-annealing-and-tempering/); [Alleima discusses welding effects for a 301-equivalent strip](https://www.alleima.com/en/technical-center/material-datasheets/strip-steel/alleima-12r11/).

No numeric XY tolerance, flatness, burr-height or edge-radius limit has been approved. Request the achievable values and proposed edge condition for review; do not silently add a general tolerance. No sharp edge or burr may damage the fitted insulation. Perform metal work before adhesive/dielectric assembly, preserving the net source section and accepted thickness.

The insulating contact pad and liner are excluded from these two cutting profiles. Existing S1 interface allocations remain references: the shoe contact pad is nominally 0.21 mm including adhesive and must be measured/finished per mounted switch. The nominal remaining allocation is 0.19-0.23 mm before printed and mounted-height uncertainty. The lower support liner is proposed at 0.08-0.10 mm, with a 1.10 mm nominal root packet and measured 0-0.07 mm shim allocation. These figures do not approve actual coverage, dielectric performance, edge protection, retention, flatness, clamp preload or assembled fit.

All 72 native PCB features / 68 purchased PCB references, actual board fit, supplier pack, root-joint displacement, switch endpoint and physical structural qualification remain open. The frozen S1 strength screening and its limitations still apply. No supplier message, order or fabrication instruction has been sent.

## Reproduce and verify

From this folder, use Blender 5.2 for extraction and Python with ReportLab for drawing creation:

```powershell
blender -b -t 2 --python extract_profiles.py
python make_drawings.py
```

A full data audit uses `pypdf` and `ezdxf==1.4.4` and requires a fresh exact-PDF visual review record after regenerating the PDF. Poppler `pdftoppm` creates the review images. The extraction script deliberately requires the frozen S1 readiness hash; a different source checkpoint needs a new engineering review, not a bypassed assertion.

To verify the delivered package and its source bindings with standard Python only:

```powershell
python verify_manufacturing.py --verify
```

The original M2 package remains untouched and still has its separate `package_m2.py --verify` check. Fabrication, material lot/process, native fit and physical qualification flags remain false throughout this package.
