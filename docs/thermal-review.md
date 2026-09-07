# AURA A03 thermal and purchasing review

Reviewed 2026-09-08. Scope: a protected 150 mAh sourcing target, the 48 × 28 × 10 mm A03 body, and its reserved **20.5 × 28 × 3.3 mm** battery volume. This report proposes a concrete charger change for the hardware author; it does not certify an assembled pack, enclosure, or fabricated PCB. No hardware source was edited by this reviewer.

## Decision

Retain BQ25185 and add an independent hot-limit comparator in its charge-enable path. Use a conservative temperature window with charging stopped by 40°C, leaving margin below the candidate cell's 45°C limit. The original direct 10 kΩ NTC has a roughly 60°C hot threshold and is unsuitable for that cell.

The best documented pack candidate found is **FPBattery / DNK 302025, 150 mAh**, file A/FP2025-7490, version 01. It is a manufacturer-listed protected pack, not a qualified purchase selection. Its drawing gives **27 ± 1 mm length including PCM**, nominal 20 mm width and 3 mm thickness, and 100 mm leads. A03 accommodates its documented length; maximum width, thickness, swelling, wire routing, NTC attachment, actual availability and a controlled purchase drawing remain unresolved. Do not treat “302025” as the complete pack dimensions. [Manufacturer preliminary datasheet](https://www.fpbattery.com/wp-content/uploads/2024/06/fpbattery-302025-3.7V-150mAh-Lithium-Polymer-Battery-Specification.pdf), [manufacturer product page](https://www.fpbattery.com/3-7v-150mah-lithium-polymer-battery/).

The sheet specifies 4.2 V charging, 30 mA recommended / 75 mA maximum charge current, 0–45°C charging and 150 mA maximum continuous discharge. Its PCM overcurrent threshold is 3–5 A, so the PCM does not enforce the 150 mA continuous discharge limit. Peak system current and fault protection still need review. The sheet does not specify permitted charger-voltage tolerance: obtain acceptance of the charger's **4.221 V maximum** before treating its 4.2 V setting as qualified.

## Exact proposed circuit

Keep the existing power path and 24 kΩ ILIM/VSET selection. Change R1 from 4.02 kΩ to **5.62 kΩ, 1%**: 53.38 mA nominal; conservative maximum `300 / (5620 × 0.99) × 1.10 = 59.31 mA`, below 75 mA. The former resistor can reach 82.92 mA by the same calculation. This uses the complete ±10% current-accuracy bound; do not stack the separate KISET spread again. The August 2026 datasheet recommends an extra ISET RC below 50 mA, so a 6.04 kΩ / 49.7 mA substitution alone is not recommended here. [BQ25185 Rev.B, pp.7,12,16](https://www.ti.com/lit/ds/symlink/bq25185.pdf).

Suggested additional parts and connections:

| Item | Connection |
|---|---|
| NTC | Exact **Semitec 103AT-2**, thermally attached to the cell; one lead to GND, the other to J2 NTC. This is an added sensor; the candidate pack sheet does not include one. |
| Series resistor | **3.30 kΩ, 1%**, between J2 NTC and a new `TS_MON` net; `TS_MON` connects to BQ25185 pin 6. No parallel compensation resistor. |
| U9 | **TLV6700DDCR**, DDC/SOT-23-6: pin 5=VSYS, 2=GND, 4=INB−=`TS_MON`, 3=INA+=GND, 1=OUTA=NC, 6=OUTB=`TEMP_ALLOW_SINK`. Add local 100 nF from 5 to 2. |
| Q1 | **DMG2302UK-7**, SOT-23: gate pad 1=`CHG_ALLOW`, source pad 2=`TEMP_ALLOW_SINK`, drain pad 3=BQ `/CE`. Verify symbol-to-footprint pad numbering during implementation. |
| Charge enable | Pull BQ `/CE` up to VSYS with **10 kΩ**. Remove the old `/CE` pulldown and direct MCU connection. U1 pad 45/P0.23 drives Q1 gate as `CHG_ALLOW`; add a **10 kΩ gate-to-GND pulldown**. HIGH permits charging, LOW disables. |

This gate arrangement lets firmware deny permission without overriding the comparator. At a safe temperature OUTB sinks, and an enabled Q1 pulls `/CE` low. When hot, OUTB releases and `/CE` rises. Do not reverse Q1 source/drain: its body diode must point from OUTB toward `/CE`. The MOSFET has specified on-resistance at VGS=2.5 V; when OUTB is at its 250 mV maximum, a 3 V gate still provides 2.75 V drive. At approximately 0.45 mA pullup current, Q1 voltage drop is negligible against the 0.4 V `/CE` low threshold. [Diodes DMG2302UK datasheet, pp.1–2](https://www.diodes.com/assets/Datasheets/DMG2302UK.pdf), [TLV6700 pin map, electrical characteristics and truth table](https://www.ti.com/lit/ds/symlink/tlv6700.pdf).

**Firmware contract:** configure P0.23 LOW immediately on boot and keep it LOW during reset/brownout and faults. Only set HIGH after supplies have been stable for at least 1 ms. The comparator requires up to 450 µs above 1.8 V before its output is valid. A depleted battery can still boot from the charger SYS power path. Default-disabled charging therefore requires functioning firmware, including recovery from a depleted cell; verify that behavior.

## Bias behavior and calculated margins

BQ25185 specifies TS bias as 36.5–39.5 µA with an adapter present, without conditioning it on `/CE`. TI's family FAQ explicitly describes constant current and says the TS source cannot be disabled in Charger/Adapter mode. This supports using the TS voltage while charging is disabled; no pulsed adapter-mode bias or enable deadlock was identified. Battery-only behavior must not be used as charging-mode evidence. Scope the actual device through dock connection, `/CE` transitions and power loss before release. [TI BQ2518x FAQ, including BQ25185](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/1603144/faq-bq2518x-how-does-the-ts-pin-work-for-battery-temperature-monitoring).

The following are **conditional worst-case calculations**, not measured cutoff temperatures. They use the manufacturer's nominal resistance table, a specified procurement/assembly acceptance band of **±3% resistance at 0°C and 40°C**, 1% series resistance, full charger/comparator thresholds, and a conservative ±25 nA comparator input-current budget. Semitec lists R25 and B25/85 tolerances of 1%; the complete R/T acceptance band, assembly drift and lifetime drift need supplier confirmation or qualification. The ±3% band is a design requirement, not a claimed manufacturer guarantee.

| Check | Calculation | Result |
|---|---|---|
| Cold stop at 0°C | `(27.280k × 0.97 + 3.300k × 0.99) × (36.5µ − 25n)` | **1.08435 V**, above the BQ cold-entry maximum 1.0575 V by **26.85 mV**. |
| Hot stop by 40°C | `(5.827k × 1.03 + 3.300k × 1.01) × (39.5µ + 25n)` | **0.36896 V**, below TLV6700 falling-threshold minimum 0.387 V by **18.04 mV**. |
| Room-temperature permission | `(10k × 0.97 + 3.300k × 0.99) × (36.5µ − 25n)` | **0.47297 V**, above its 0.404 V maximum rising threshold. |
| Shorted sensor | `(3.300k × 1.01) × (39.5µ + 25n)` | **0.13174 V**, so the added comparator denies permission. |
| Open sensor | TS rises to the charger's clamp | BQ cold fault denies charging; confirm during fault injection. |

The nominal hot-entry resistance is `0.3945/38µ − 3300 = 7.082 kΩ`, between Semitec's 30°C and 40°C entries, roughly 34–35°C. Cold-entry resistance is `1.0075/38µ − 3300 = 23.213 kΩ`, between 0°C and 10°C. Cold hysteresis moves restart to approximately 10°C. These are an intentionally narrow operating window; no claim is made that charging remains available throughout 0–45°C. Use Semitec's actual R/T table for qualification, rather than extrapolating B25/85 below 25°C. [Semitec AT thermistor datasheet, specifications and R/T table](https://www.semitec-global.com/uploads/2022/01/P12-13-AT-Thermistor.pdf).

Simple series/parallel compensation around the original thermistor cannot independently narrow the BQ's fixed hot/cold ratio to the desired range. The old advice to use 100 Ω and 352 kΩ was corrected in the TI thread and must not be copied. [TI BQ25185 threshold discussion](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/1472003/bq25185-ntc-temperature-threshold).

The electrical cutoff margin does not establish cell-to-sensor thermal lag or wearable surface temperature. Verify the attached sensor in the closed enclosure, including simultaneous charging/radio/haptic activity. At 5.25 V input, 3.0 V battery and 59.31 mA charge current, battery-charge-path dissipation alone can approach 133 mW; system-path loss is additional. The IC's internal junction regulation is not a cell-temperature limit.

## LRA candidate and remaining purchasing checks

**Precision Microdrives C08-00A** is the strongest documented motor candidate found: maximum diameter 8.1 mm, maximum thickness 2.75 mm, nominal 240 Hz, rated 1.2 Vrms, maximum 1.25 Vrms, maximum rated current 41 mA, typical terminal resistance 32.6 Ω. Its 100 ± 2 mm AWG34 leads need trimming/strain relief. A03's 8.5 mm pocket accommodates the maximum body diameter. [Manufacturer C08-00A drawing and electrical specification](https://www.precisionmicrodrives.com/datasheets/C08-00A%20-%20datasheet%20-%20002.pdf).

This fits the DRV2605L frequency/impedance operating region, but **replace the old generic 1.8 Vrms assumption**. The retrieved motor sheet is marked for prototype sampling and advises a voltage reduction with automatic resonance tracking, with application-specific validation. Treat 0.84 Vrms (70% of 1.2 Vrms) as a conservative initial engineering target, not a validated DRV register setting. Derive rated/overdrive register values from the actual drive mode and calibrate with the installed motor; do not permit generic auto-calibration overdrive to exceed its limit. [DRV2605L datasheet](https://www.ti.com/lit/ds/symlink/drv2605l.pdf). Production availability and final approved motor specification remain purchasing checks.

The hardware author updated the NAND package during this review; its source now records ZE 8 × 6 mm and 3.4 × 4.3 mm exposed pad against Rev.R. This reviewer did not independently retrieve that revision and makes no separate package signoff. The wider electrical review is in [electrical-review.md](electrical-review.md).

Before fabrication/charge qualification, close the controlled pack drawing and voltage tolerance; implement and verify the above circuitry in the exported schematic/netlist/PCB; then test thermistor substitution at the stated resistance corners, open/short sensor, startup with depleted battery, hot dock connection, MCU reset and thermal lag. No clean ERC/DRC or functional firmware result is asserted by this report.
