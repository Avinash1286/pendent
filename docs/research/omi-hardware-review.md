# Omi hardware lessons for a buildable AURA

Reviewed 2026-09-09. Omi source is pinned to [`f42089f53c8010dd971b3702ece05a231c9c0c66`](https://github.com/BasedHardware/omi/tree/f42089f53c8010dd971b3702ece05a231c9c0c66), inspected locally without executing upstream code. AURA geometry is the released [native A03 PCB](../../hardware/native/aura-a03.kicad_pcb), SHA-256 `b9ec8ebf1a0afaa7563ed4838e145cebb4f14055f71e25b2dbcb0329b0180064`. No board, schematic, footprint, enclosure, fabrication file or rule was changed by this review. No purchase or supplier submission was made.

## Decision

**Use a XIAO nRF52840 Sense based development wearable to validate daily capture first; retain AURA A03 as the custom-board engineering reference and make A04 an assembly-focused revision.** Omi's triangle approach is a useful build method. Its consumer PCB is a substantially more difficult manufacturing project, not a shortcut to an inexpensive first wearable.

A03's fabrication package is technically suitable for **bare-board prototype quotation and CAM review**, with the specified stack and mixed drill tools. It is **not ready for an unconditional assembled-board order or wearing as a qualified battery product**. Besides the 78 open assembly courtyard findings, the focused manufacturer-tolerance check below identifies a real MK2/U7 clearance problem that nominal model inspection missed. Finished-device charging contacts, dock, protected pack/NTC assembly and physical qualification remain incomplete.

## What the two Omi builds actually teach

| Design | Evidence from the pinned source | Implication for AURA |
| --- | --- | --- |
| Triangle v2 / development build | XIAO nRF52840 Sense, Adafruit 5769 Audio BFF, microSD, a 250 mAh battery candidate, button, speaker and printed case. The guide explicitly calls it a developer version with incomplete testing/firmware coverage. | Validate capture, phone transfer, battery behavior and wearability using assembled modules before spending another iteration on dense custom PCBA. The speaker is optional for AURA's note-taking purpose. |
| Consumer | nRF5340 and nRF7002 in WLCSP, dual T5838 microphones, NAND, IMU, custom 150 mAh round cell, mainboard + charging board + FPC, machined/molded/printed parts. | Industrial miniaturization also requires supply, assembly, acoustic and dock engineering. Copying the exterior or Gerbers does not reproduce that process. |
| AURA A03 | 24 × 42 mm, four layers, nRF52840 radio module, dual bottom-port PDM microphones, 128 MiB NAND, hardware privacy switch/indicator, power-path charger, gauge and haptic driver. 61 PCB references include four copper-contact features; assembly exports contain 57 component candidates. | The radio module and larger passives are sensible prototype choices. The remaining limitation is placement/process margin and unqualified external assemblies, rather than lack of additional feature ICs. |

Sources: [triangle v2 assembly and correction guide](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/hardware/triangle%20v2%20w%20memory/README.md), [consumer hardware README](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/hardware/consumer/README.md), [AURA native release description](../../hardware/native/README.md).

The Omi BOM has **88 rows**, including assembly headers, PCB blanks, mechanical parts and grouped designators. It does not mean 88 placements comparable to AURA's 61 references. Summing the mainboard designator rows 3–57 gives **136 component placements**, including **93 explicitly described 0201 passives**. The consumer docs specify a 21 × 21 mm, 0.6 mm, four-layer mainboard with blind/buried vias and approximately 0.4 mm pitch WLCSPs. JLCPCB's standard rigid capability currently excludes blind/buried vias, so those consumer files need an appropriate HDI supplier or a redesign. [Pinned consumer BOM](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/omi/hardware/consumer/bom/omi-bom.csv), [pinned electronics guide](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/docs/doc/hardware/consumer/electronics.mdx), [manufacturer rigid capabilities](https://jlcpcb.com/capabilities/pcb-capabilities).

Two documentation lessons matter. First, Omi's consumer README calls CSNP4GCR01 storage **4 Gbit**, while the electronics/assembly docs call the same part **8 GB**. This review does not resolve the part's capacity; neither statement should become an AURA requirement without the exact device data. Second, the triangle guide documents a speaker correction because its original 5 V connection had no supply in battery mode. Validate every operating state with the battery and USB/dock separately. The simpler build guide's switched battery return also means charging requires its switch to be ON; that behavior is specific to that build and should not be copied as AURA's privacy architecture. [Pinned general build guide](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/docs/doc/assembly/Build_the_device.mdx).

Omi explicitly separates standalone recording from transcription: its DevKit 2 still needs the app for transcription processing. Keep the same architectural honesty for AURA. Current AURA firmware records locally and transfers audio; the pendant does not run an LLM. At 16 kHz mono PCM16 its ideal storage ceiling is about **66 minutes**, before overhead/reserves, and current firmware prohibits simultaneous capture and transfer. These are practical first-wear workflow limits that deserve attention before adding Wi-Fi, an IMU or a speaker. [Pinned DevKit 2 specification](https://github.com/BasedHardware/omi/blob/f42089f53c8010dd971b3702ece05a231c9c0c66/docs/doc/hardware/DevKit2.mdx), [AURA firmware behavior and limitations](../../firmware/README.md).

## The 78 courtyard findings, classified

The [native DRC report](../../hardware/native/review/drc.json), SHA-256 `b512ea20202e4734e6bd2a9306cafee5359a523bebb04810c13149c481d6c3d3`, has 78 `courtyards_overlap` errors, zero unconnected items and zero schematic-parity findings. This review independently confirmed every pair by native filled `F.CrtYd` polygon collision. All 78 are on the front; none belongs to the four underside copper-contact features.

The [pair-by-pair classification data](aura-a03-courtyard-classification.json) records UUIDs, packages, drawing bounds, minimum different-net copper-pad distances and dispositions. Groups below are mutually exclusive triage categories: the first special assembly feature takes priority, so, for example, a microphone/SOT pair is counted under acoustic LGA.

| Review group | Pairs | Smallest Fab drawing-envelope gap | Required disposition |
| --- | ---: | ---: | --- |
| Radio module | 13 | 0.180 mm | Check module seating, perimeter joints, nozzle/rework access and maximum envelope. Preserve the antenna keepout. |
| Acoustic LGA | 11 | 0.020 mm | **Fix MK2/U7 tolerance conflict.** Review acoustic-port registration, paste arcs, gasket and cleaning process for both microphones. |
| Mechanical switch | 8 | 0.100 mm | Check body/terminal maximums, actuator motion, assembly sequence and rework access around SW1/U7 and SW1/U8. |
| Exposed-pad leadless IC | 10 | 0.130 mm | Confirm maximum body/lead spans, exposed-pad stencil coverage, thermal mass and inspection/rework plan. |
| Fine-pitch gull-wing IC | 3 | 0.250 mm | Review lead spans and stencil/AOI access; a large plastic-body gap can coexist with tightly spaced lands. |
| SOT IC/transistor | 14 | 0.175 mm | Check actual lead and mold-flash envelopes; close Q1/R1, R9/U7, C17/Q1 and C18/U4 first. |
| Silicon capacitor, excluding mic pair | 1 | 0.280 mm | C4/R10: verify specialty-part handling and its actual stencil process. |
| Diode/LED, excluding higher-priority pairs | 3 | 0.300 mm | Verify package/terminal maximums, polarity inspection and access. |
| Standard chip passives | 15 | 0.125 mm | Check chip dimensional/placement tolerance and fillets; C17/R3 has least drawing margin. These are lower-complexity review candidates, not automatic waivers. |

The Fab number is the Euclidean separation between axis-aligned bounds of all restored `F.Fab` graphic shapes, **including drawing stroke widths**. Positive numbers prove those drawing envelopes do not intersect; they do not represent guaranteed production clearance. Some Fab drawings omit protruding leads and use nominal bodies. The separate [mechanical envelope audit](../../enclosure/PACKAGE-ENVELOPES.md) already states this limitation. No error in the restored courtyard definitions was demonstrated; reducing or removing them would conceal an unresolved process requirement.

JLCPCB's assembly guidance describes component spacing for placement tolerance, stencil separation, inspection and rework. Its published examples include 0.15 mm between 0402 chips, 0.18 mm for 0402/0603, 0.2 mm for chip/SOT and 1 mm for chip/QFN. These are supplier process recommendations, not the same quantity as copper clearance. This review does **not** mechanically classify all 78 against that table: several package classes are absent, and the site's measurement illustration was not available for visual verification in this session. Obtain a package-specific measurement/acceptance interpretation from the selected assembler, including maximum dimensions. [JLCPCB assembly-spacing guidance, updated June 12, 2026](https://jlcpcb.com/help/article/minimum-spacing-for-smd-components).

### A real tolerance conflict: MK2 and U7

MK2's native footprint anchor is `(108.500, 90.4575)` mm; the restored microphone **body centre** is `(108.500, 90.730)` after the documented 0.2725 mm converter-origin correction. U7's body centre is `(107.450, 94.050)` mm. Their body spans overlap along X, and centre separation along Y is **3.320 mm**. Using the footprint's nominal 3.50 mm microphone length and 2.90 mm SOT body length gives 0.120 mm nominal outline clearance, or 0.020 mm after both 0.10 mm graphic strokes are included.

The microphone manufacturer specifies length **3.50 ± 0.10 mm**. TI's DBV0005A drawing gives the exact regulator package's body length maximum **3.05 mm**. The maximum-body calculation is:

`3.320 − (3.600 + 3.050) / 2 = −0.005 mm`

Thus allowed maximum body envelopes overlap by 5 µm even at perfect nominal placement. This is a tolerance-envelope conflict, not a claim that every sample will collide. Placement error and TI's separate mold-flash allowance would require additional margin. **A04 should increase this separation and recheck routing, mic alignment and the case; assembler sign-off alone cannot create missing geometric margin.** A one-off measured engineering deviation would need controlled component dimensions and verified placement, not a blanket courtyard exclusion. [Knowles manufacturer datasheet Rev B, mechanical specifications page 9, distributor mirror](https://www.mouser.com/datasheet/2/218/sph0641lu4h_1_revb-3313002.pdf#page=9), [TI TLV755P Rev D, DBV package drawing page 41](https://www.ti.com/lit/ds/symlink/tlv755p.pdf#page=41).

## What can be fabricated now, and what still blocks a wearable

| Stage | Current decision | Evidence or missing item |
| --- | --- | --- |
| Bare A03 boards | **Reasonable experimental fabrication candidate after supplier CAM review.** | Four-layer through-via construction; zero native copper/connectivity/parity findings. Use the provided 0.8 mm stack, ENIG and actual 175 × 0.20 mm plus 2 × 0.15 mm plated drills, with two 0.50 mm NPTH acoustic holes. This does not imply the populated design is qualified. |
| Routine A03 PCBA order | **Hold pending geometry/process review.** | MK2/U7 maximum-body conflict, 77 other open courtyard findings, exact-part availability/alternate review, stencil, panel rails/fiducials, placement rotation and inspection plans. Some can be process-approved; maximum-body interference must be corrected or controlled explicitly. |
| Bench bring-up | **Possible after a reviewed assembly and current-limited power plan.** | SWD pads, native electrical source and buildable firmware exist. First-article inspection and functional measurements are still required. |
| Battery-powered wear | **Not yet qualified.** | Exact protected pack, charger voltage acceptance, attached NTC, charging faults, peak current, thermal lag, enclosure tolerance, acoustic seals, RF on body, sweat/contact insulation and mechanical retention remain unresolved. |
| Complete dock | **Incomplete accessory design.** | PCB contact features and an alignment jig exist; exact rear contacts, retention, rated pogo parts and a complete protected 5 V dock design do not. |

The completed pad audit checked **25,158 different-net SMD pairs** against 0.15 mm with zero violations; its smallest inter-component result is C16/U8 at 0.165 mm. The via audit checked **177 vias** in 88,500 actual copper/paste comparisons with zero intersections. Those results are still bound to the unchanged native PCB hash. They remove specific bare-board/stencil risks; they do not clear package tolerances or assembly access. [Final manufacturing checks](../../hardware/native/review/manufacturing-checks.json), [exact pad audit](../../hardware/native/review/native-smd-pad-spacing-audit.json), [via/paste audit](../../hardware/native/review/native-via-aperture-audit.json).

The external BOM remains engineering candidates: the 150 mAh DNK302025 pack has an unresolved controlled maximum envelope and charger-voltage tolerance; Semitec103AT-2 attachment/R–T acceptance and the C08-00A LRA drive are unqualified. Current firmware deliberately disables charging and haptics. These are actual remaining tasks, not features a buyer can presently assume work. [External BOM](../../hardware/output/external-bom.csv), [thermal review](../thermal-review.md), [firmware qualification requirements](../../firmware/README.md#charging-and-haptic-qualification).

### Compact fabrication handoff

For **bare-board review only**, send the [four copper layers, mask, legend, outline and Gerber job files](../../hardware/native/fabrication/gerbers/), [separate PTH/NPTH drills and maps](../../hardware/native/fabrication/drills/), and [IPC-D-356 netlist](../../hardware/native/fabrication/aura-a03.ipc), together with the [native README](../../hardware/native/README.md) and [manufacturing checks](../../hardware/native/review/manufacturing-checks.json). All plot/drill coordinates use the board centre; do not mirror drills or apply a second origin offset.

Specify **24 × 42 mm, R10 corners; four-layer FR-4; 0.8 mm nominal finished thickness; ENIG; green mask; white legend; through vias with normal tenting**. Preserve stack **JLC04081H-3313**: 35 µm top copper / 99.4 µm prepreg / 15.2 µm inner copper / 500 µm core / 15.2 µm inner copper / 99.4 µm prepreg / 35 µm bottom copper, material sum 0.7992 mm. Use all three actual drill tools: 0.20 mm PTH (175), 0.15 mm PTH (2) and 0.50 mm NPTH (2). No blind/buried vias, via fill/capping or controlled-impedance qualification is claimed. Have CAM confirm the mixed drills, stack and small-board panel handling; published capability does not constitute approval of these files.

**Withhold a routine PCBA order.** The [57-placement BOM](../../hardware/native/assembly/bom.csv), [component-centre file](../../hardware/native/assembly/component-centres.csv) and [paste layers](../../hardware/native/assembly/stencil/) are review inputs, not approved assembly instructions. MK2/U7 fails the maximum-body tolerance check; the other 77 courtyard pairs remain open; final sourcing, stencil/panel/process details and the external battery/contact assemblies are not closed.

Before A04 PCBA release:

1. **Placement:** fix MK2/U7 with maximum dimensions plus assembly tolerance, then resolve or specifically justify all other courtyard pairs through geometry/process review; regenerate routing and mechanical evidence.
2. **Dock:** complete the keyed, protected 5 V USB-C dock and select exact rear contacts, pogo pins, retention and assembly method; verify shorts, polarity and repeated docking.
3. **BOM and battery:** freeze purchasable exact-MPN components and controlled protected-pack/NTC/harness specifications; approve alternates by electrical, land-pattern and assembly checks, then qualify charging before enabling it.
4. **Assembly:** agree the panel, stencil, feeder/rotation conventions, microphone cleaning restrictions, exposed-pad inspection and first-article tests with the assembler. Keep the original 78 DRC findings visible until their actual dispositions are recorded.

## Chosen first-person build path

1. **Bring up a XIAO nRF52840 Sense based mule on USB power.** The manufacturer documents a 21 × 17.8 mm board with onboard PDM microphone, radio, USB and battery charger. Use a supported board firmware target; AURA's current HEX/pin map is not drop-in XIAO firmware. Confirm audio reaching the companion, reconnection, capture indication and power-loss behavior before miniaturizing. [Seeed's board documentation](https://wiki.seeedstudio.com/XIAO_BLE/).
2. **Add storage only through a demonstrated interface.** For phone-independent notes, the triangle's microSD/Audio BFF arrangement is an available reference, but its firmware and battery-mode correction must match the build. For AURA firmware reuse, a W25N01GV breakout and an explicit board/driver port preserve the existing journal design at the cost of more wires. Select one implementation and test repeated unplug/reconnect and interrupted recordings; do not infer compatibility from using the same MCU.
3. **Make the first case accessible and intentionally roomier.** Use a printed shell with a clear mic path, insulated lead routing, strain relief and accessible USB/SWD. It will need its own fit model; A03's 48 × 28 × 10 mm finished-case model is not guaranteed to contain stacked development boards. Preserve visible recording state and an explicitly defined physical privacy action. The XIAO's stock microphone wiring does not reproduce AURA's independent microphone-power cutoff.
4. **Add a matched protected battery after checking charger current, voltage and temperature behavior.** Use a controlled pack specification and an assembled harness; charge off body during engineering evaluation. Measure workload current/runtime and closed-case temperatures before treating this as a daily wearable. Only then transfer the validated experience to a revised custom board.

This path minimizes fine-pitch soldering and lets a person learn whether capture, transfer and everyday interactions work. It does not grant the mule AURA's privacy guarantees or make an untested lithium pack safe by association with Omi.

## Prioritized A04 changes

| Priority | Concrete change | Acceptance evidence |
| --- | --- | --- |
| P0 | Re-layout the MK2/U7 area using maximum package dimensions and placement tolerance; then work through the remaining 77 pairs. Begin with SW1/U7, R3/U2, U5/U6 and the radio perimeter. Grow the board/case if needed. | No worst-case package interference; native DRC remains visible; each courtyard pair is removed by actual spacing or has a specific reviewed process disposition. Re-run electrical, pad/paste and enclosure checks after moves. |
| P0 | Close one exact protected-cell/NTC/harness specification before enabling charging. Match 4.221 V charger maximum, charge/peak current, temperature limits and swelling envelope. | Supplier-controlled drawings and ratings plus measured open/short NTC, hot/cold, depleted-cell dock startup, reset and thermal-lag tests. Do not remove the independent hot cutoff to save area. |
| P0 | Complete a simple keyed USB-C powered dock and exact rear contact assembly. Include input protection/current limiting, reverse/misalignment handling, contact ratings and cable strain relief. | Schematics/CAD/BOM and measured contact resistance, short circuit, reverse docking, repeated mating and retention. AURA's dock contacts are not yet a charger product. |
| P1 | Retain the nRF52840 module, omit Wi-Fi/IMU/speaker unless the validated capture flow requires them, and keep the independent hardware privacy cutoff/indicator. | Reliable note capture/transfer and RF measurements in the final case with the actual cord/chain and wearer. |
| P1 | Choose stocked exact-MPN BOM entries and assembler-approved alternates before routing A04. Treat C3/C4 silicon capacitors, microphones, NAND, module and switches as special sourcing/process items. | Approved vendor list, packaging/reel format, lifecycle/lead time checked when ordering, and pin/land/reflow verification for every alternate. Evaluate a simpler mic decoupling option only after acoustic noise/bias testing; do not silently substitute the silicon parts. |
| P1 | Ask the assembler to define panel rails, fiducials, board support, nozzle access, stencil thickness/apertures, exposed-pad coverage, mic-port cleaning restrictions and inspection. Keep underside wire/contact soldering as a documented separate operation. | Reviewable panel/stencil/assembly drawings and a first-article report. Avoid fragile battery leads and flux contamination around the acoustic holes. |
| P1 | Remove the two 0.15 mm drill exceptions in A04 if routing space permits and retain ordinary through-via construction. Preserve separation from exposed pads and paste. | Fresh native DRC, matching Gerbers/drills and via/paste audit; no HDI or filled-via process introduced merely to chase visual compactness. |
| P2 | Make test access, firmware recovery and final assembly order explicit; validate the working battery/USB/dock states before sealing. Measure capture endurance and transfer time rather than adding more storage by headline. | Repeatable SWD/pogo fixture, test firmware/results, acoustic recordings, stress/reconnect tests and measured runtime. |

## Reproduce the read-only geometry classification

The portable [classification script](../scripts/audit-aura-courtyards.py) requires **KiCad 10's Python with `pcbnew`**; this run used KiCad 10.0.4. From the repository root on Windows:

```powershell
& 'C:/Program Files/KiCad/10.0/bin/python.exe' docs/scripts/audit-aura-courtyards.py
```

On another system, use the Python interpreter provided/configured with KiCad's `pcbnew`. The script reads only committed native board, DRC, manifest and pad-audit files, writes the classification JSON, and verifies all input hashes stayed unchanged. Paths resolve relative to the repository, independent of the shell's working directory; `--board`, `--drc`, `--manifest`, `--pad-audit` and `--output` allow explicit paths. It contains A03-specific reference, orientation, DRC-count and expected-board-hash guards and the cited manufacturer maximum dimensions. A later board revision requires a fresh engineering review; passing a different hash alone does not make those assumptions valid. No temporary checkout or upstream Omi execution is needed to reproduce this classification.

## Complete pair register

Every row remains an open native courtyard finding. `Fab gap` is the drawing-envelope lower bound described above; `pad gap` is the smallest **different-net** SMD copper separation for that footprint pair, not all-net assembly clearance. Values are millimetres. The maximum-body failure at MK2/U7 takes precedence over its positive nominal drawing gap.

| Pair | Review group | Fab gap | Pad gap |
| --- | --- | ---: | ---: |
| C10/U4 | SOT IC/transistor | 1.200 | 0.226 |
| C14/U7 | SOT IC/transistor | 1.200 | 0.225 |
| C15/U7 | SOT IC/transistor | 0.650 | 0.525 |
| C17/Q1 | SOT IC/transistor | 0.200 | 0.622 |
| C18/U4 | SOT IC/transistor | 0.200 | 0.440 |
| C18/U9 | SOT IC/transistor | 1.350 | 0.390 |
| C2/Q1 | SOT IC/transistor | 1.358 | 0.351 |
| C7/U4 | SOT IC/transistor | 1.500 | 0.175 |
| C9/Q1 | SOT IC/transistor | 0.450 | 0.300 |
| D2/U4 | SOT IC/transistor | 1.150 | 0.725 |
| Q1/R1 | SOT IC/transistor | 0.175 | 0.220 |
| Q1/R16 | SOT IC/transistor | 1.475 | 0.295 |
| Q1/R4 | SOT IC/transistor | 1.230 | 0.255 |
| R9/U7 | SOT IC/transistor | 0.180 | 0.430 |
| C14/MK2 | acoustic LGA | 0.670 | 0.833 |
| C3/MK1 | acoustic LGA | 0.175 | 0.400 |
| C4/MK2 | acoustic LGA | 0.275 | 0.500 |
| C5/MK1 | acoustic LGA | 0.375 | 1.699 |
| C6/MK1 | acoustic LGA | 0.225 | 0.375 |
| MK1/U2 | acoustic LGA | 0.220 | 0.457 |
| MK2/R10 | acoustic LGA | 0.350 | 0.320 |
| MK2/R13 | acoustic LGA | 0.255 | 0.668 |
| MK2/R15 | acoustic LGA | 0.255 | 0.430 |
| MK2/R9 | acoustic LGA | 0.350 | 0.725 |
| MK2/U7 | acoustic LGA | 0.020 | 0.487 |
| C1/LED1 | discrete diode/LED | 0.300 | 0.265 |
| C10/D1 | discrete diode/LED | 0.300 | 0.800 |
| C7/D1 | discrete diode/LED | 0.700 | 0.941 |
| C11/U5 | exposed-pad leadless IC | 0.650 | 0.324 |
| C5/U2 | exposed-pad leadless IC | 0.400 | 0.365 |
| C9/U3 | exposed-pad leadless IC | 0.650 | 0.550 |
| LED1/U5 | exposed-pad leadless IC | 0.200 | 0.350 |
| R17/U2 | exposed-pad leadless IC | 0.380 | 0.355 |
| R3/U2 | exposed-pad leadless IC | 0.130 | 1.025 |
| R5/U2 | exposed-pad leadless IC | 0.625 | 0.395 |
| R6/U2 | exposed-pad leadless IC | 0.625 | 0.481 |
| U3/U9 | exposed-pad leadless IC | 0.200 | 0.600 |
| U5/U6 | exposed-pad leadless IC | 0.150 | 0.700 |
| C12/U6 | fine-pitch gull-wing IC | 0.250 | 0.600 |
| C13/U6 | fine-pitch gull-wing IC | 1.500 | 0.175 |
| C16/U8 | fine-pitch gull-wing IC | 1.000 | 0.165 |
| C12/SW1 | mechanical switch | 0.500 | 0.325 |
| C13/SW2 | mechanical switch | 0.950 | 0.225 |
| C14/SW1 | mechanical switch | 0.750 | 1.925 |
| C16/SW1 | mechanical switch | 0.500 | 2.247 |
| Q1/SW2 | mechanical switch | 1.700 | 0.375 |
| SW1/U7 | mechanical switch | 0.100 | 1.900 |
| SW1/U8 | mechanical switch | 0.250 | 1.925 |
| SW2/U6 | mechanical switch | 0.776 | 0.775 |
| C1/U1 | radio module | 0.450 | 0.590 |
| C15/U1 | radio module | 0.700 | 1.025 |
| C2/U1 | radio module | 0.650 | 0.625 |
| LED1/U1 | radio module | 0.350 | 0.325 |
| R10/U1 | radio module | 0.325 | 0.470 |
| R3/U1 | radio module | 0.425 | 0.570 |
| R6/U1 | radio module | 0.180 | 0.530 |
| R8/U1 | radio module | 0.180 | 0.530 |
| R9/U1 | radio module | 0.325 | 0.470 |
| U1/U2 | radio module | 0.200 | 1.445 |
| U1/U5 | radio module | 0.450 | 0.475 |
| U1/U6 | radio module | 1.450 | 0.500 |
| U1/U7 | radio module | 1.300 | 0.700 |
| C4/R10 | silicon capacitor | 0.280 | 0.330 |
| C1/C2 | standard chip passive | 0.250 | 0.216 |
| C10/C7 | standard chip passive | 0.900 | 0.743 |
| C14/R13 | standard chip passive | 0.825 | 0.245 |
| C17/R3 | standard chip passive | 0.125 | 0.380 |
| C17/R4 | standard chip passive | 0.400 | 0.170 |
| C2/R16 | standard chip passive | 0.580 | 0.205 |
| C2/R7 | standard chip passive | 0.475 | 0.245 |
| C2/R8 | standard chip passive | 0.475 | 0.245 |
| C5/C6 | standard chip passive | 0.600 | 0.215 |
| C9/R1 | standard chip passive | 0.255 | 0.205 |
| C9/R2 | standard chip passive | 0.255 | 0.205 |
| R11/R14 | standard chip passive | 0.610 | 0.220 |
| R11/R21 | standard chip passive | 0.600 | 0.190 |
| R11/R5 | standard chip passive | 0.600 | 0.190 |
| R13/R15 | standard chip passive | 0.600 | 0.190 |
