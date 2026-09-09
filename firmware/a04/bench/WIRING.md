# A04 external bench wiring review

This is an **unpowered design review for an nRF52840 DK bench fixture**, dated 2026-09-09. No fixture has been assembled, powered, flashed or measured. These connections are not the AURA PCB pinout, a fabrication release or permission to wear a battery-powered prototype. The separate bench application must remain an explicitly selected build target.

The first useful experiment is two external PDM microphones recording into a real W25N01GV, with physical microphone power control and UART export. Use a USB-powered DK and a common low-voltage rail; no battery, charger or dock is part of this experiment.

## Pins agreed with the bench application

Signal names, rather than physical header pin numbers, are authoritative. Match the actual PCA10056 board revision and silkscreen before wiring. Nordic identifies P1 as the power/ground connector and P2–P6/P24 as GPIO access; default UART, crystal, NFC, button/LED and onboard flash connections must be preserved. [Nordic connector reference](https://docs.nordicsemi.com/r/bundle/ug_nrf52840_dk/page/ug/dk/connector_if.html)

| Function | DK GPIO / Arduino name | External connection | Reset / idle requirement |
| --- | --- | --- | --- |
| PDM clock | P0.30 / A4 | Clock-buffer input A; buffer output to both mic CLK pins | External 100 kΩ pulldown at A; firmware stops PDM before normal power-off |
| PDM data | P0.31 / A5 | Both mic DAT pins, shared stereo bus | Input only, no MCU pull-up; 100 kΩ pulldown on the shared bus |
| NAND SCK | P1.15 / D13 | W25N CLK | SPI mode 0; begin characterization at 1 MHz |
| NAND MOSI | P1.13 / D11 | W25N DI / IO0 | No other bus master |
| NAND MISO | P1.14 / D12 | W25N DO / IO1 | Input only |
| NAND CS | P1.12 / D10 | W25N /CS | Active low; external 10 kΩ pull-up to NAND VCC |
| Mic power command | P1.03 / D2 | Physical allow contact, then load-switch ON | Active high; load-switch ON has an external 100 kΩ pulldown |
| Physical permission sense | P1.04 / D3 | Second linked contact to GND | Pull-up; low means allow, high/open means privacy or disconnected switch |
| Capture status | P0.13 / onboard LED1 (`led0`) | Existing DK LED/resistor | Active low; no extra external LED load |
| UART console | P0.06 TX, P0.08 RX, P0.05 RTS, P0.07 CTS | Existing interface MCU / USB virtual serial port | UART0 at 115200; do not connect these to the fixture |

The SPI mapping is Zephyr's `spi3` Arduino mapping. Disable default `spi1`, whose pinctrl otherwise claims P0.30/P0.31, and disable `pwm0`, which otherwise claims the status LED. Keep `i2c1` and `uart1` disabled. Do not share these pins with shields, trace outputs or another overlay. The original PDM sample enables PDM without disabling `spi1`; copying that sample alone is insufficient for this combined application. [Zephyr 4.2.0 DK DTS](https://raw.githubusercontent.com/zephyrproject-rtos/zephyr/v4.2.0/boards/nordic/nrf52840dk/nrf52840dk_nrf52840.dts), [pinctrl](https://raw.githubusercontent.com/zephyrproject-rtos/zephyr/v4.2.0/boards/nordic/nrf52840dk/nrf52840dk_nrf52840-pinctrl.dtsi), [PDM sample](https://raw.githubusercontent.com/zephyrproject-rtos/zephyr/v4.2.0/samples/drivers/audio/dmic/boards/nrf52840dk_nrf52840.overlay).

Do not substitute the DK's onboard MX25R64 QSPI NOR for W25N01GV NAND. Its wiring, command set and storage geometry differ. This fixture does not require cutting the onboard-memory solder bridges. [Nordic onboard-memory reference](https://docs.nordicsemi.com/r/bundle/ug_nrf52840_dk/page/ug/dk/hw_external_memory.html)

## Supply and actual component route

Use the DK's **VDD and GND**, with its SoC supply selection in the VDD position and normal USB/interface operation. Confirm the actual revision's switch names against its manual. The USB-derived VDD supply is nominally 3 V. Do not connect the fixture to 5 V, VDDH, a lithium cell, or an independently powered 3.3 V rail while the DK GPIO rail remains 3 V. All fixture grounds return to DK GND. The initial supply check target is **2.85–3.15 V at each powered device**; this is a project bench window, not a manufacturer tolerance. Measure at load, including NAND program/erase transients. [Nordic DK power description](https://infocenter.nordicsemi.com/pdf/nRF52840_DK_User_Guide_v1.4.1.pdf)

| Item | Named route | Review result |
| --- | --- | --- |
| Microphones | One **KAS-700-0164** two-pack of SPH0641LU4H-1 microphones on flex, with **two KCA2733** assembled flex-to-coupon adapters | Matches MK1/MK2 in the actual A04 schematic and architecture. Explicit output-level specifications permit a positive static DAT margin at the common 3 V rail. |
| NAND | W25N01GVSFIG, 16-pin SOIC, on a passive pin-numbered SOIC16-to-header adapter | Winbond operating supply 2.7–3.6 V. Identify the package and orientation; do not use the eight-pad WSON numbering for SOIC16. |
| Mic load switch | TPS22918DBVR on a passive SOT23-6 adapter or an electrically equivalent reviewed fixture | GPIO controls ON only; the switched current comes from VDD. |
| Clock isolation | SN74LVC1G125DBVR on a passive SOT23-5 adapter | Buffer supply follows MIC_VDD. Its powered-off protection is required for the proposed physical power cut. |

The KAS-700-0164 two-pack is listed as the assembled SPH0641LU4H-1 flex route; KCA2733 provides its passive adapter. Both were listed in stock when checked on 2026-09-09 (32 packs and 194 adapters). This is availability evidence, not a reservation or delivery guarantee. No parts have been ordered. [Exact microphone kit](https://www.digikey.com/en/products/detail/syntiant/KAS-700-0164/17878612), [exact adapter](https://www.digikey.com/en/products/detail/syntiant/KCA2733/16644481), [manufacturer kit selection guide](https://www.knowles.com/docs/default-source/default-document-library/mic-selection-guide-v121222.pdf).

Use the **KCA2733 six-position coupon interface**, not the eight-position flex connector numbering:

| Coupon contact | Marking / signal | Bench connection |
| --- | --- | --- |
| 1 | P / power | MIC_VDD |
| 2 | O / digital DATA | Shared DAT to P0.31 |
| 3 | G / ground | Common GND |
| 4 | LR / SELECT | GND on one adapter, MIC_VDD on the other |
| 5 | Unused for PDM | Leave disconnected |
| 6 | K / bit clock | Isolated clock-buffer output |

AN18 explicitly defines this pinout and distinguishes the assembled KCA2733 from its bare KCB2734 PCB. It includes a 100 nF bypass capacitor. Use the adapter's marked contacts with strain-relieved flying wires, or the specified Sullins EBM03DSEN-S243 mating connector; confirm continuity to the marked nets before applying power. [Manufacturer AN18, pages 1–2](https://www.knowles.com/docs/default-source/default-document-library/an18-knowles-flex-circuit-and-coupons-for-testing_updated.pdf). Insert each flex with copper contacts face down and latch closed as shown in the [manufacturer Muskie guide, page 5](https://www.mouser.com/catalog/specsheets/knowles%20corp_06052019_KAS-33100-0004%20Muskie%20Users%20Guide%20rev29may19.pdf). The Muskie controller itself is not needed and must not simultaneously drive these nets.

The selected microphone accepts 1.62–3.6 V. Normal PDM clock is **1.024–2.475 MHz**, with 40–60% duty below 2.4 MHz and a 3 ns maximum clock edge time. Startup allowance is 50 ms. A 1.032 MHz or 1.280 MHz PDM setting is within that range; **1.000 MHz is not**. NAND SCK remains a separate 1 MHz signal. Verify the compiled driver's selected clock/decimation and actual PCM rate; a requested 16 kHz alone does not prove either. Keep acoustic ports clear, retain local 100 nF bypassing, and characterize both channels separately. [Knowles SPH0641LU4H-1 Rev B, electrical/interface tables](https://www.mouser.com/datasheet/2/218/sph0641lu4h_1_revb-3313002.pdf)

The same interface table specifies DATA **VOH ≥ MIC_VDD − 0.45 V** and **VOL ≤ 0.45 V** at 2 mA. Against Nordic's VIH ≥0.7×VDD and VIL ≤0.3×VDD, the equal-rail static high and low margins are each `0.3 × VDD − 0.45 V`, at least **0.405 V** for VDD≥2.85 V. Requiring MIC_VDD to remain no more than 50 mV below DK VDD leaves **0.355 V** high margin; ground shift, noise and transient loading consume that budget. These are calculated interface margins using published limits, not measurements or a full-temperature production guarantee. Scope the actual DATA half-cycles and clock edges, confirm load/current limits, and measure rail difference. [Nordic GPIO limits](https://docs-be.nordicsemi.com/bundle/nRF52-Series-PS/raw/resource/enus/nRF52840_PS_v1.0.pdf?save_local=true).

The initially considered Adafruit/MP34DT01-M route is **not selected**: its combined 0.65×VDD /0.35×VDD I/O table did not establish positive margin against Nordic's input limits. It must not be substituted without a new interface review. [ST MP34DT01-M table 3](https://www.st.com/resource/en/datasheet/mp34dt01-m.pdf)

## Physical microphone privacy fixture

Use a **mechanically linked two-pole maintained switch**, wired so both contacts close only in the allow position. An ordinary momentary button or a firmware input alone does not implement this power cut.

```text
DK VDD ---- TPS22918 VIN             VOUT ---- MIC_VDD ---- both adapters P
DK GND ---- TPS22918 GND                         +--------- clock-buffer VCC
P1.03 ----- switch pole A ---- ON
                             +-- 100 kΩ -- GND
P1.04 ----- switch pole B ---- GND
  +-------- pull-up to DK VDD (configured GPIO; external 10 kΩ recommended)

P0.30 ----- buffer A          buffer Y --------- both microphone CLK
  +-- 100 kΩ -- GND           +-- 100 kΩ -- GND
                             buffer /OE ------- GND
                             buffer GND ------- GND
```

TPS22918 DBV pins are VIN1, GND2, ON3, CT4, QOD5, VOUT6. Place at least 1 µF ceramic on VIN, leave CT unconnected for the first fixture, and connect QOD to VOUT. Keep total switched capacitance below 200 µF for this QOD connection; the proposed microphone and adapter bypassing is below that limit. Its ON thresholds are ≥1 V high and ≤0.5 V low. The external pulldown makes reset and an open contact disable the switch. Check adapter orientation and continuity before power. [TI TPS22918 Rev C, pin functions and QOD](https://www.ti.com/lit/ds/symlink/tps22918.pdf)

SN74LVC1G125 DBV pins are /OE1, A2, GND3, Y4, VCC5. Add 100 nF directly across VCC/GND. The buffer operates from 1.65–5.5 V and specifies powered-off leakage with VCC=0; this prevents treating a live MCU clock wired directly to an unpowered mic as valid isolation. It does **not** prove isolation throughout rail decay, contact bounce, or every component fault. Measure cutoff timing and backfeed with P0.30 deliberately toggling while the physical switch is off. The application's normal stop sequence remains necessary. [TI SN74LVC1G125 Rev U, sections 5 and 7.3.2](https://www.ti.com/lit/ds/symlink/sn74lvc1g125.pdf)

Privacy sense is fail-closed for an open wire; a short to ground is not diagnosed by this two-wire sense. DAT is directly connected to a high-impedance MCU input in this fixture: accidentally configuring that pin as an output or enabling a pull-up can back-power the microphones and is not covered by the clock buffer. A04's proposed dual buffer also isolates DATA; this bench fixture has not implemented that additional fault boundary. The status LED reports application state and is not an independent electrical witness of microphone power. Do not claim instantaneous cutoff, fault-tolerant privacy, or verified recording indication from this wiring review.

## W25N01GV connections

For the **SOIC16 SF package only**: /HOLD1 and /WP9 each get 10 kΩ to VCC2; GND10 goes to common ground; /CS7 goes to P1.12; DO8 to P1.14; DI15 to P1.13; CLK16 to P1.15. Leave NC3–6 and NC11–14 disconnected. Place 100 nF ceramic and 4.7 µF local bulk bypass across VCC/GND as fixture starting values. These capacitance values and the initial 1 MHz bus are engineering choices requiring measurement, not a vendor-qualified layout. Keep wiring short with adjacent ground returns.

Use standard single-data-line SPI, mode 0, active-low CS. Pulling WP/HOLD high avoids unintentional hold/protection assertions; it does not override software/OTP protection. The driver must validate chip identity, ECC/configuration, factory bad-block markers and BBM state. Preserve unknown source contents; never mass-erase a populated chip to make initialization pass. [Winbond manufacturer datasheet Rev R, sections 3.4, 4 and 7, hosted by Mouser](https://www.mouser.com/datasheet/2/949/Winbond_Electronics_09072023_W25N01GV_Rev_R_070323-3313374.pdf)

## Evidence required before calling the bench functional

1. Record exact DK revision, component markings, adapter continuity, opposite SEL straps, supply polarity and absence of shorts with power removed.
2. Measure VDD/MIC_VDD and current with microphones disabled, enabled, and during NAND traffic. Verify rail limits, local decoupling and absence of backfeed. A shared USB console is not a wearable power measurement.
3. Scope clock frequency/duty/edge integrity and DAT setup/hold plus high/low levels at the receiving pin. Confirm the calculated static budget survives actual rail difference, loading and noise; a decoded audio file alone does not prove those conditions.
4. Verify the physical switch removes mic power despite a stuck-high software command and a toggling upstream clock, then verify firmware stops capture on a rising/open permission input. Record measured cutoff and rail discharge timing; no result is assumed here.
5. Capture distinguishable left/right sound, export the actual NAND-backed archive, independently decode it, compare exact receipts and repeat cold recovery without deleting the original capture. Apply power-fault tests only to explicitly disposable test recordings.

The local source identities and the unmeasured review status are recorded in [wiring-review.json](wiring-review.json). Supply compatibility and pin ownership have been reviewed; complete electrical, acoustic, privacy, flash-endurance and physical operation remain unverified.
