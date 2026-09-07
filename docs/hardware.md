# AURA EVT-A · hardware engineering dossier

**Status: connected engineering prototype, not approved for fabrication or sale as working hardware.** The product renders show the intended appearance. They do not demonstrate acoustic quality, endurance, RF certification, thermal comfort or a functioning AI service.

The primary source is [`hardware/src/AuraPendant.tsx`](../hardware/src/AuraPendant.tsx), with component definitions in [`design.ts`](../hardware/src/design.ts). The build produces real Circuit JSON, a logical netlist, BOM, placements and editable KiCad exports. The exact latest test/route results live in [`hardware/output`](../hardware/output); an empty placement-error array is not a routed-board DRC pass.

## Architecture and deliberate UX choices

| Block | Selected design | Purpose |
|---|---|---|
| Compute / radio | Raytac MDBT50Q-1MV2, nRF52840 | Low-power BLE, PDM capture, DMA, storage and controls |
| Audio | Two SPH0641LU4H-1 PDM MEMS microphones |17mm spaced acoustic inputs; opposite channel select levels |
| Offline storage | W25N01GVZEIG,1Gbit SPI NAND |128MiB nominal capture buffer; ECC/bad-block management required |
| Charge / power path | BQ25185DLHR |75mA target charge,4.2V chemistry,100mA dock limit, pack NTC monitoring |
| System rail | TLV75530PDBVR |3.0V rail from system/battery voltage |
| Microphone rail | Separate TLV75530PDBVR plus DPDT switch | Firmware can request capture; physical slider can remove and ground microphone power |
| Signal isolation | SN74LVC2G125DCUR | Powered from microphone rail; Ioff blocks PDM clock/data back-power when off |
| Battery awareness | MAX17048G+T10 | State-of-charge and low-battery alert over I2C |
| Feedback | DRV2605LDGSR, external8mm LRA envelope | Distinct tactile start, stop, bookmark and error patterns |
| Controls | Front record button, side bookmark, mechanical privacy slider | Eyes-free deliberate capture, with no background pre-roll |
| Privacy light | Amber LED and1k resistor on microphone supply | Hardware indication of energized microphones; no separate software-off control |
| External interface | Keyed magnetic dock,3 rear ENIG contacts |5V limited input, two grounds; no exposed USB receptacle |
| Service |6 SWD pogo pads, battery and LRA wire pads | Factory programming, recovery and first-article testing |

AI transcription, summaries, search and task extraction belong in a paired phone/optional cloud service. No on-device language model, completed phone app or deployed AI backend is included. Audio is captured locally before any transfer, so a phone disconnect must not destroy a note.

## Mechanical contract

Body target:30mm wide ×40mm tall ×12mm thick, excluding the necklace loop and actuator protrusions. PCB:24mm ×34mm,4mm corner radius,0.8mm FR4, four copper layers. Positive Y points to the necklace loop. Side retention rails avoid board mounting holes.

- PCB underside Z1.15mm, top Z1.95mm; module height2.05mm gives topZ4.00mm against front inner ceilingZ4.70mm.
- Protected cell target20×25×5mm, center(0,−4,−1.9)mm. This is an envelope requirement, not a qualified purchasing part. It leaves0.55mm nominal PCB clearance and0.40mm rear clearance before adhesives/tolerances.
- Microphone acoustic holes at(−8.5,+8.5) and(+8.5,+8.5)mm;0.5mm NPTH per source land pattern. The microphone bodies sit atY9.27mm. Wraparound acoustic gasket channels from board underside to front apertures require tuning and leak tests.
- Front record(0,−6)mm; amber LED approximately(0,−1)mm; privacy switch(9.5,−0.2)mm, rotated90°. The9.1×3.6mm DPDT body needs a mechanical actuator link to the external slider.
- An8.5×8.5mm top component-free allocation centered(+6,−12)mm surrounds the8mm LRA envelope. A local front-wall pocket and thin insulating adhesive are needed. Tolerance closure and motor sourcing remain open.
- Antenna region Y>12.7mm excludes copper on all layers. The enclosure over it must be RF-transparent; battery, chain and metal decoration proximity need final antenna validation. The keepout is a provisional placement constraint pending complete Raytac integration-guide review.

## Electrical targets and calculations

| Item | Calculation / design assumption | Evidence level |
|---|---|---|
| Charge current |300AΩ /4.02kΩ =74.6mA nominal | Datasheet equation; not measured |
| Charge limit |24kΩ on ILIM/VSET selects100mA input and4.2V battery | Datasheet configuration |
| Cell charge rate |74.6mA /200mAh =0.37C | Assumes a qualified200mAh cell |
| Peak charger dissipation example |(4.65−3.7)V ×0.0746A ≈71mW | Assumes Schottky drop0.35V; excludes system-path losses |
| Capture budget |22mA planning allowance;160mAh usable /22mA ≈7.3h | Engineering estimate; no battery-life claim |
| Offline audio baseline |128MiB ×0.85 /8000bytes/s ≈3.96h |16kHz mono4-bit ADPCM; codec not integrated |
| Optional compressed target |128MiB ×0.85 /(24000/8) ≈10.6h |24kb/s codec, still requires benchmark and firmware |
| Recording light |(3.0−about2.0)V /1kΩ ≈1mA | LED forward voltage and brightness to measure |

The LDO topology prioritizes simplicity, low noise and compactness. It loses efficiency relative to a switching regulator and drops out near an exhausted cell. Firmware must close notes before its validated voltage threshold. Haptic peaks are supplied by the battery/system rail, not the3.0V rail. The charger does not replace cell qualification or an appropriate protected battery pack.

## Build and verification evidence

- The placement build contains59 components,240 pads and41 logical nets. Its initial constrained layout cleared tscircuit pad-overlap and pad-clearance error checks; the LRA allocation then drove a further placement revision. Always use the newest `placement-validation.json` for the final count.
- `logical-checks.json` verifies unique references, no connected NC pins, all declared nets having at least two endpoints, the microphone power/isolation path, both mic channel selections, charge settings and case-hole alignment.
- Seven executable capture-controller tests cover offline capture, bookmarks, privacy cutoff, full storage, failed commits, low-battery stop and privacy toggles during an in-flight commit. These validate reference policy logic only, not firmware on a device.
- The capacity autorouter was stopped after a long silent attempt with approximately442 CPU seconds and no usable result. The source now selects KRT WASM with a bounded120,000-iteration budget per connection. Its actual output and unresolved findings are recorded separately; no clean routing result is inferred from tool completion.
- KiCad MCP inspection returned no loaded board, opening the exported board timed out, and its Python backend exited. An independent KiCad10 CLI DRC was attempted as fallback. If no report is present, that check did not complete and must not be described as passed.
- The installed tscircuit ecosystem has upstream TypeScript source errors and npm audit findings. Runtime compilation/exports and logical tests are recorded separately. `npm-audit.json` preserves the dependency report; no blanket force upgrade was applied to a moving PCB toolchain.

## Exact release blockers

1. Complete copper routing, define and fill return planes, connect all ground pads with intentional low-impedance paths, add thermal/stitch vias and verify independent KiCad connectivity/DRC with no unexplained violations.
2. Compare every exported land pattern to its retained original and datasheet: pin numbering, diode polarity, flash exposed-pad handling, switch commons/orientation, microphone annulus, solder paste and pad corner geometry. The exporter was observed to default KiCad board thickness to1.6mm despite0.8mm source intent; review/normalize the export before fabrication.
3. Finish ERC pin electrical types and power flags. Generic chip wrappers currently leave source warnings about pin roles, refdes conventions and courtyards. This is not a completed electrical-rule signoff.
4. Select exact passive, battery, NTC and LRA purchasing parts. Many passive BOM entries are explicitlyTBD. Verify effective capacitor values under bias, cell charge/discharge/temperature limits, reverse dock behavior and pack protection. No purchase-ready BOM is claimed.
5. Bench-test power sequencing, microphone cutoff and signal back-power, visible LED failure behavior, charge hot/cold faults, LDO dropout, haptic calibration and skin-facing thermal comfort.
6. Integrate and test PDM/DMA, recoverable NAND storage with ECC, timestamps, signed firmware update, protected BLE bonding and resumable transfers. Prove corruption recovery by interrupting power and links.
7. Validate the assembled acoustics, clothing rustle, wind, RF/antenna performance with chain and body present, ESD, mechanical durability and applicable market compliance. Module certification does not certify this finished wearable.

## Primary documentation reviewed

- [tscircuit introduction](https://docs.tscircuit.com/), [installation](https://docs.tscircuit.com/intro/installation), [CLI quickstart](https://docs.tscircuit.com/intro/quickstart-cli), [board API](https://docs.tscircuit.com/elements/board), [chip API](https://docs.tscircuit.com/elements/chip), [footprints](https://docs.tscircuit.com/elements/footprint), [keepouts](https://docs.tscircuit.com/elements/keepout).
- [Raytac MDBT50Q-1MV2 product and integration documents](https://www.raytac.com/product/ins.php?index_id=24). Product dimensions and architecture were reviewed; direct PDF retrieval was inconsistent/403, so full integration-guide validation remains open.
- [TI BQ25185 datasheet](https://www.ti.com/lit/ds/symlink/bq25185.pdf), [TLV755P datasheet](https://www.ti.com/lit/ds/symlink/tlv755p.pdf), [DRV2605L datasheet](https://www.ti.com/lit/ds/symlink/drv2605l.pdf), [SN74LVC2G125 datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc2g125.pdf).
- [Analog Devices MAX17048 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/max17048-max17049.pdf).
- [Winbond W25N01GV documentation](https://www.winbond.com/hq/support/documentation/?__locale=en&pno=W25N01GV); the documentation index was reviewed, but a complete current flash mechanical PDF still needs comparison against the chosen land pattern.
- [Knowles SPH0641LU4H-1 manufacturer datasheet link](https://www.knowles.com/docs/default-source/model-downloads/sph0641lu4h-1-revb.pdf). The official link was unavailable during retrieval; pad mapping was crosschecked in the installed KiCad10 official library. Current manufacturer supply status and final acoustic specifications require review.

The original KiCad library footprints are retained with attribution. No component ordering, manufacturing submission or hardware certification was performed.
