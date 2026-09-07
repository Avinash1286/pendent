# Component documentation provenance

Manufacturer PDFs downloaded for local review are excluded from this repository.
Use these original sources to reproduce the review. Retrieval took place on
7–8 September 2026; obtain the current revision before procurement.

| Source | Review scope / limitation |
|---|---|
| [tscircuit documentation](https://docs.tscircuit.com/) | Installation, CLI, board/chip/footprint/keepout APIs |
| [Raytac MDBT50Q-1MV2](https://www.raytac.com/product/ins.php?index_id=24) | Exact module selection; manufacturer PDF hosted by [Espruino](https://www.espruino.com/datasheets/MDBT50Q-1M.pdf) supplements a blocked direct download |
| [BQ25185 Rev.B, August 2026](https://www.ti.com/lit/ds/symlink/bq25185.pdf) | Power-path pins, 4.2 V setting, 53.38 mA nominal charge, TS thresholds and capacitor requirements |
| [TLV755P](https://www.ti.com/lit/ds/symlink/tlv755p.pdf) | 3V regulator family; final package/pin inspection required |
| [DRV2605L](https://www.ti.com/lit/ds/symlink/drv2605l.pdf) | Haptic driver pins and LRA interface |
| [SN74LVC2G125](https://www.ti.com/lit/ds/symlink/sn74lvc2g125.pdf) | Buffer pinout and partial-power-down Ioff behavior |
| [MAX17048 / MAX17049](https://www.analog.com/media/en/technical-documentation/data-sheets/max17048-max17049.pdf) | Gauge pin functions and application topology |
| [W25N01GV documentation index](https://www.winbond.com/hq/support/documentation/?__locale=en&pno=W25N01GV), [Winbond Rev.R PDF mirror](https://www.marthel.pl/katalog/W25N01GV%20Rev%20R%20070323.pdf) | Manufacturer content, 3 July 2023: pins and ZE 8 × 6 mm WSON, exposed pad 3.4 × 4.3 mm; EP may float or connect to ground; no exposed vias underneath |
| [Winbond 2025 selection guide](https://www.winbond.com/export/sites/winbond/product-selection-guide/file/2025-Product-Selection-Guide-Winbond-Code-Storage-Flash-Memory.pdf) | Confirms W25N01GVZEIG uses 8 × 6 mm WSON |
| [SPH0641LU4H-1 official Rev.B link](https://www.knowles.com/docs/default-source/model-downloads/sph0641lu4h-1-revb.pdf), [Knowles Rev.A PDF mirror](https://xonstorage.z8.web.core.windows.net/pdf/knowles_sph0641lu4h1_apr22_xonlink.pdf) | Official link unavailable. Manufacturer Rev.A content confirms pinout, timing and Class II capacitor warning; original KiCad land retained. Current revision/supply status remains a review item |
| [TLV6700 Rev.B](https://www.ti.com/lit/ds/symlink/tlv6700.pdf) | DDC pin map, comparator truth table, input-current/threshold bounds and 450 µs startup maximum |
| [DMG2302UK](https://www.diodes.com/assets/Datasheets/DMG2302UK.pdf) | SOT-23 gate/source/drain numbering and on-resistance at 2.5 V |
| [Semitec AT thermistor](https://www.semitec-global.com/uploads/2022/01/P12-13-AT-Thermistor.pdf) | 103AT-2 nominal resistance table. Assembled ±3% acceptance at 0°C/40°C is a design requirement, not an asserted vendor guarantee |
| [TI TS bias FAQ](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/1603144/faq-bq2518x-how-does-the-ts-pin-work-for-battery-temperature-monitoring), [TI threshold discussion](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/1472003/bq25185-ntc-temperature-threshold) | Adapter-mode TS bias and why simple series/parallel compensation does not independently set both limits |
| [FPBattery DNK302025-150 preliminary sheet](https://www.fpbattery.com/wp-content/uploads/2024/06/fpbattery-302025-3.7V-150mAh-Lithium-Polymer-Battery-Specification.pdf) | Protected pack candidate, actual 27 ± 1 mm length including PCM, 75 mA charge maximum and 0–45°C range; controlled tolerances/NTC/voltage acceptance unresolved |
| [Precision Microdrives C08-00A](https://www.precisionmicrodrives.com/datasheets/C08-00A%20-%20datasheet%20-%20002.pdf) | 8 mm LRA candidate; 1.2 Vrms rated, 1.25 Vrms maximum, 240 Hz; prototype supply and drive calibration require qualification |
| [C&K KMR2](https://www.ckswitches.com/media/1479/kmr2.pdf), [KMR211NGULCLFS product](https://www.ckswitches.com/products/switches/product-details/Tactile/KMR2/KMR211NGULCLFS%C2%A0/) | No-ground-tab, ultra-low-current variant; 1.2 N and 0.20 ± 0.10 mm electrical travel |
| [Murata BBSC 0402 100 nF Rev.3.00](https://www.murata.com/products/productdata/8814108606494/SICAP-BBSC424610.pdf?1632454218000=), [manufacturer-page mirror](https://www.alldatasheet.com/html-pdf/1397988/MURATA1/939113424610-T3N/2141/6/939113424610-T3N.html) | Exact 939113424610-T3N order code, 3.8 V rating, 1.2 × 0.7 × 0.4 mm die and 0.7 mm pad pitch; direct PDF intermittently unavailable |
| [Murata reflow assembly Rev.1.42](https://www.murata.com/-/media/webrenewal/products/capacitor/siliconcapacitors/assemblynotepdf/assembly-reflow.ashx?cvid=20260729042609000000&la=en) | Mask-defined/NSMD guidance and Table 1 minimum land dimensions. Authored land requires actual mask-registration and stencil qualification |
| [KEMET C0805C106K8PACTU](https://search.kemet.com/download/specsheet/C0805C106K8PACTU) | Exact 10 µF / 10 V / 0805 X5R SYS reservoir candidate; effective biased capacitance and aging remain validation requirements |
| [Freerouting 2.4.1](https://github.com/freerouting/freerouting/releases/tag/v2.4.1), [CLI source](https://github.com/freerouting/freerouting/blob/v2.4.1/docs/command_line_arguments.md) | Local headless routing, DSN/SES interchange, bounded passes and standalone DRC |

Ordinary resistor selection uses Yageo RC0402FR 1% parts. Manufacturer sheets follow `https://yageogroup.com/component-documentation/download/specsheet/<MPN>`; examples checked include RC0402FR-0710KL, RC0402FR-07100KL, RC0402FR-074K7L, RC0402FR-071KL and RC0402FR-0733RL. Values added for the reviewed thermal circuit follow the same ordering system and require purchasing confirmation.

Ordinary capacitor candidates are KEMET C0402C104K4RACTU, C0402C103K5RACTU, C0603C105K4RACTU, C0603C225K8RACTU and C0603C475K8PACTU. Manufacturer spec sheets are under `https://yageogroup.com/download/specsheet/<MPN>`. Do not substitute a smaller package or dielectric without electrical, bias and acoustic review.

The public repository includes authored design sources and review reports, plus
KiCad footprints with their upstream library license/attribution in
[`../library/NOTICE.md`](../library/NOTICE.md). Inclusion is not a purchasing,
manufacturing or certification approval.
