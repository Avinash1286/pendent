# AURA EVT-A03 · hardware engineering dossier

**Status: authored electrical design, placement and routing work; not fabrication-ready.** The A03 capsule is 48 × 28 × 10 mm and the board is 24 × 42 × 0.8 mm with R10 corners. The sources include real component pin maps, footprints, schematics and net assignments. Product renders are appearance references; they do not establish a working device, acoustic quality, endurance, RF performance or manufacturing approval.

The primary design is [AuraPendant.tsx](../hardware/src/AuraPendant.tsx), with the electrical definition in [design.ts](../hardware/src/design.ts). Generated artifacts and exact validation reports are in [hardware/output](../hardware/output). A placement check is distinct from routed-board connectivity and DRC.

## Architecture and user experience

| Block | Selected design | Purpose |
|---|---|---|
| Compute / radio | Raytac MDBT50Q-1MV2, nRF52840 | Bluetooth LE, PDM acquisition, DMA, storage and controls |
| Audio | Two Knowles SPH0641LU4H-1 PDM MEMS microphones | 17 mm acoustic spacing; opposite channel select levels |
| Microphone bypass | Murata 939113424610-T3N silicon capacitors | 100 nF local bypass using silicon dielectric |
| Offline storage | W25N01GVZEIG, 1 Gbit SPI NAND | 128 MiB nominal; internal ECC and bad-block management required |
| Charge / system power | BQ25185DLHR | 53.38 mA nominal charge, 4.2 V setting and 100 mA dock input limit |
| Charge temperature gate | TLV6700DDCR, DMG2302UK-7, series 3.30 kΩ and external Semitec 103AT-2 | Independent hot cutoff with default-off firmware permission |
| System regulator | TLV75530PDBVR | 3.0 V rail from the system/battery path |
| Microphone regulator | Separate TLV75530PDBVR plus DPDT switch | Firmware requests capture; physical slider removes and grounds microphone power |
| Signal isolation | SN74LVC2G125DCUR | Powered from microphone rail; Ioff limits PDM clock/data back-power while off |
| Battery awareness | MAX17048G+T10 | State of charge and low-battery alert over I2C |
| Haptics | DRV2605LDGSR; Precision Microdrives C08-00A candidate | Distinct capture, stop, bookmark and error feedback |
| Record control | KMR211NGULCLFS underneath the flush black face | One press to record/stop; doublepress bookmark; no extra external button |
| Privacy control / light | JS202011JCQN slider; amber LED wired to microphone supply | Physical microphone disconnect and visible energized-microphone state |
| External interface | Three rear contact pads; keyed magnetic dock concept | 5 V limited input with two ground contacts; dock contact hardware remains unqualified |
| Service | Six SWD pads, battery and motor wire pads | Programming, recovery and first-article testing |

AI transcription, summaries, search and task extraction run in a paired phone or opt-in cloud service. The pendant does not run a language model. No completed phone application or AI service is included. Local capture must survive phone and network disconnection. See the [firmware contract](../hardware/firmware/contract.md) and its explicit implementation limits.

The compiled firmware configures stereo PDM capture at 1.280 MHz with ratio 80, yielding 16 kHz, then averages left and right into PCM16 mono. It waits 50 ms after the microphone rail turns on and discards two 40 ms startup buffers. This is implemented behavior in an untested image, not measured audio performance or beamforming.

## Mechanical contract

Coordinates are millimetres; positive Y points toward the necklace loop. The PCB has no mounting holes and is held by side clips. Its top is Z0.65 and underside Z−0.15 in the A03 enclosure.

- The radio is centred at (0, 8), with 10.5 × 15.5 mm body and 2.05 mm height. Its unused VBUS pin 32 is grounded; VDD/VDDH use normal-voltage mode and DCCH is open.
- NAND U2 uses the correct **ZE 8 × 6 × 0.8 mm WSON**, not the smaller 6 × 5 package. Its centre is (−8.55, 3.20), rotated 90°, giving 6 × 8 mm assembled X/Y body dimensions. The 3.4 × 4.3 mm exposed pad is grounded, as allowed by Winbond Rev.R; do not put exposed vias underneath it.
- The protected 150 mAh candidate is FPBattery/DNK 302025. Its drawing gives 27 ± 1 mm length including PCM, nominal 20 mm width and 3 mm thickness. The case reserves **20.5 × 28 × 3.3 mm** centred at Y−3. Maximum width, thickness, swelling, attached NTC, leads and permitted voltage tolerance remain procurement/qualification gates. The model is not a qualified cell drawing.
- Microphone acoustic holes are (−8.5, 8.5) and (8.5, 8.5), each 0.5 mm NPTH. Microphone bodies are at Y9.27 because the bottom port is offset. Wraparound acoustic gasket channels to the front require acoustic and leak testing.
- SW2 is at (0, −6). Its low-current, no-ground-tab KMR211 variant has 1.2 N nominal force and 0.20 ± 0.10 mm electrical travel. The rigid full-face paddle has 0.35 mm nominal travel and 0.02 mm rest gap, providing 0.33 mm potential switch motion. Return gasket, stack tolerances and permissible overtravel still require physical validation.
- The amber LED is at (0, −1); privacy switch SW1 is at (9.5, −0.2), rotated 90°. The elongated external slider mechanically drives SW1.
- An 8.5 × 8.5 mm front-side component exclusion at (6, −12) reserves the motor. C08-00A maximum body is 8.1 mm diameter and 2.75 mm thickness. Its rated voltage is 1.2 Vrms, maximum 1.25 Vrms; generic 1.8 V settings must not be used.
- All-layer copper exclusion extends from Y11.95 to the new PCB top at Y21. It preserves Raytac's 3.8 mm antenna-end exclusion. Use RF-transparent polymer and a nonconductive top retainer; the chain, finishes and body proximity require RF testing.
- J1 and the three rear contact surfaces agree at X−3, 0, 3 and Y−19, diameter 1.7 mm. They sit below the enlarged cell allowance, leaving 0.55 mm nominal separation to the contact carrier. A short contact-tail path is geometrically possible; actual contacts, tails, strain relief, dock polarity and wear remain unqualified.

## Electrical calculations and evidence limits

| Item | Calculation / assumption | Evidence |
|---|---|---|
| Charge current | 300 AΩ / 5.62 kΩ = 53.38 mA nominal | TI equation; not measured |
| Conservative charge maximum | 300 / (5620 × 0.99) × 1.10 = 59.31 mA | Full current-accuracy bound; below candidate pack's 75 mA maximum |
| Charge rate | 53.38 mA / 150 mAh = 0.356 C | Assumes qualified 150 mAh pack |
| Input / battery setting | 24 kΩ selects 100 mA and 4.2 V | Datasheet configuration; 4.221 V maximum needs pack approval |
| Capture budget | 120 mAh assumed usable / 22 mA = 5.45 h | Unmeasured engineering budget |
| Implemented storage format | PCM16 mono × 16 kHz = 32,000 bytes/s | Compiled firmware; approximately 66 min ideal journal capacity before other metadata/bad blocks, not hardware-tested |
| Future ADPCM target | 128 MiB × 0.85 / 8000 bytes/s = 3.96 h | 16 kHz mono 4-bit ADPCM is a planning value, not the implemented codec |
| Optional compressed storage | 128 MiB × 0.85 / 3000 bytes/s = 10.6 h | 24 kb/s codec requires implementation and benchmarking |
| Recording light | (3.0 V − approximately 2.0 V) / 1 kΩ ≈ 1 mA | Brightness and forward voltage need measurement |

The LDO topology favours compactness and low noise, with efficiency and end-of-discharge dropout tradeoffs. Haptic peaks use the system rail. Battery protection does not remove the need to check actual system peak current, fault current or cell qualification.

The original direct NTC hot threshold was approximately 59.5°C and was unsuitable for a 0–45°C cell. **A03 replaces that arrangement** with a 3.30 kΩ series resistor, TLV6700 hot comparator and series MOSFET in the active-low charge-enable path. CHG_ALLOW has a 10 kΩ default-low gate pulldown; firmware can deny permission but cannot override the comparator. Charge enable is pulled up to VSYS. Firmware waits at least 1 ms after stable power before permission. The charger's adapter-mode constant TS bias supports sensing while /CE is disabled.

The [thermal review](thermal-review.md) gives conditional cold-stop and hot-stop calculations: a specified ±3% assembled NTC resistance acceptance band at 0°C and 40°C gives 26.85 mV cold margin and 18.04 mV hot margin. This is a required acceptance band, not a claimed Semitec full R/T guarantee. Nominal hot entry is roughly 34–35°C; cold hysteresis narrows the restart window. A03 does not promise charging throughout 0–45°C. Pack voltage tolerance, sensor attachment/thermal lag, open/short faults, depleted-cell boot and actual cutoff measurements remain release gates.

C3/C4 now use exact Murata silicon parts. Their authored copper pads are 0.50 × 0.70 mm on 0.70 mm pitch, with intended 0.40 × 0.60 mm mask openings and 0.30 × 0.50 mm paste apertures. Murata's reflow note gives minimum land dimensions 0.314 × 0.514 mm and maximum gap 0.386 mm for this die; stencil thickness, mask registration and assembly leakage require qualification. This addresses the retrieved Knowles Class II warning, while acoustic performance remains untested. C9 is an exact KEMET 10 µF / 10 V 0805 part. TI requires 10 µF nominal and at least 1 µF after DC-bias derating; capacitance under actual bias, temperature and aging must be checked.

## Verification and routing evidence

The source has **61 component/PCB-feature references and 43 nets**. Four references are custom PCB contact/pad features, not purchasable SMT components. Logical tests check pin identity, defaults, thermal-gate connections, isolation, NC pins and acoustic alignment. Export checks verify all 208 authored connected logical pins against the numeric pads in the generated KiCad board, including duplicate switch lands. These do not establish routed connectivity.

The portable microphone ground ring uses 32 polygon segments; the KiCad export restores one original annular land and four paste arcs, compensating for the exporter's footprint-origin shift. The exported thickness is explicitly normalized to the authored 0.8 mm.

`placement-validation.json` retains one U1 keepout-boundary finding: the module's top ground lands end at Y11.95, exactly on the mandated keepout edge. The boundary was not weakened to silence it. Generic chip wrappers also retain role/courtyard warnings, so full ERC is not claimed.

Native KiCad schematic ERC was also run against `aura.kicad_sch`. `kicad-a03-schematic-erc.json` records **968 findings: 220 pin-not-connected errors, 494 off-grid endpoint warnings, 132 missing Custom symbol-library warnings and 122 unconnected wire-endpoint warnings**. These are material schematic-interchange failures, not a passed circuit ERC. The native schematic must be repaired and its exported netlist compared against the authored 208 connected logical pins before release. The tscircuit logical netlist and PCB numeric-net checks do not eliminate this independent failure.

`kicad-a03-final-placement-drc.json` records **65 findings: 61 generated footprint library references and 4 back-layer fabrication-text mirroring warnings, with 167 unconnected items**. It has no copper, pad, hole or board-edge violations, but contains zero tracks/vias. `export-checks.json` passes net identity and selected mic/SiCap geometry checks with no warnings; capacitor centre distances C7/C8/C9 to U3 are 2.264/2.305/2.850 mm. A short routed loop still must be verified. The independent KiCad placement DRC and standalone autorouter results must be read separately. Older A02 sessions used different geometry, and some used the former incorrect NAND package; they are historical attempts, not valid A03 routing.

The KiCad connector previously returned `success:false, cancelled:true, action:"decline"` for `import_ses`, with the message `KiCad operation 'import_ses' was not executed`. No reason was supplied. No alternate importer was used to bypass that cancellation. Consequently, a standalone SES does not establish a routed KiCad board, and the copied A02 file that was an import target remains placement-only.

Earlier routing attempts are preserved for reproducibility. KRT failed with zero copper and 199 disconnected-port findings. An older Freerouting A02 attempt generated 372 wire paths / 82 vias but retained 24 connections; it is superseded and not fabrication evidence. The A03 attempt and its exact input hash must match before any subsequent import. Project-local Freerouting 2.4.1 is used for the current attempt; installation and hash are in [hardware/README.md](../hardware/README.md).

The first saved **A03 session contains 542 wire paths and 109 vias**. Its twelve-pass in-memory routing log reached 11 remaining connections, then ended optimization at 12 remaining and 4 violations. A fresh standalone DSN + SES reload reports **nine disconnected net groups and one dangling CHG_ISET via warning**, without reproducing the four clearance findings. Reloading for refinement reports 11 airwires. These counts describe different checks; the DRC JSON groups whole disconnected nets and is not a count of individual airwires. No clean check is inferred from the serialization discrepancy. The disconnected groups are GND, SPI_CS_N, CHG_STAT1, CHG_STAT2, I2C_SDA, CHG_DISABLE, CHG_VSET, CHG_ISET and V3.

The final six-pass strict-DRC refinement completed in 7 min 24 s within its eight-minute limit. **`aura-a03-route-refine.ses` contains 545 wire paths and 109 vias.** Its in-memory router ended with **10 unconnected items and 4 violations**; the fresh standalone reload reports **eight disconnected net groups and one dangling CHG_ISET via warning**. V3 connectivity improved; the other eight groups listed above remain disconnected. Enabling strict DRC did not remove the in-memory/reload discrepancy, and no clearance pass is claimed for a native routed PCB.

`aura-a03-routing-status.json` records the final session and exact source SHA-256 values. `aura-a03-route-study.svg` renders the actual standalone four-layer session, explicitly marked unfinished. `fabrication-review-notes.md`, `assembly-bom.csv`, `cpl-top.csv` and `external-bom.csv` provide review material; they do not authorize manufacturing. Source/placement geometry remained unchanged across both A03 attempts. Further routing needs explicit work on congested charger escapes and the remaining nets, followed by complete return-plane and power-path review.

## Manufacturing release gates

1. Complete all copper connections, define/fill return planes and intentional power/thermal paths, then import into the matching board and run independent KiCad connectivity/DRC with no unexplained violations. A placement-only export must not be sent to fabrication.
2. Finish ERC electrical pin types, power flags, courtyards and generated footprint library registration. Complete pad/pin/polarity review, mic ring/NPTH and paste inspection, silicon-capacitor mask/paste checks, and assembly rotation verification. C3/C4 direct bypasses now use silicon; other Class II capacitors, including nearby C5/C6, still need acoustic placement review against Knowles guidance before assembly.
3. Qualify the complete protected pack and attached NTC, including allowed 4.221 V charge maximum, assembled resistance acceptance, cutoff temperatures, thermal lag, swelling, peak discharge and mechanical clearance. Qualify C08-00A supply status and calibrated drive limits.
4. Verify power sequencing, charging faults, depleted-cell recovery, microphone disconnect/back-power, LDO dropout, storage power-loss recovery, haptics and skin-facing temperature on real hardware. Do not infer these from the state-machine tests or render.
5. Complete and exercise the firmware/audio/storage/transfer/security functions described in the firmware package. A compiled image alone is not evidence of successful recording, Bluetooth transfer or note retention.
6. Validate assembled acoustics, clothing rustle, wind, ESD, RF with chain/body present, face/slider durability and applicable market requirements. Module certification does not certify this finished wearable.
7. After these gates, create a reviewed manufacturing release with Gerbers, plated/nonplated drill files, stackup, netlist, assembly drawings, approved BOM, component positions, stencil and fabrication notes. No fabrication-ready or purchase-ready release is currently claimed.

## Documentation provenance

Read the [source index](../hardware/sources/README.md), [electrical review](electrical-review.md) and [thermal review](thermal-review.md) for exact manufacturer links and retrieval limits. Vendor documents are not redistributed. Authored sources, reports and footprints with upstream attribution are included. No parts were ordered and no manufacturing submission or hardware certification was performed.
