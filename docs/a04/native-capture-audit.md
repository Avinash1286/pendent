# A04 native capture audit

Read-only inspection, 2026-09-09, refreshed for candidate 2 exported at 02:28:35. No CAD edits, MCP calls, ERC reruns, placement attempts or approval workarounds were performed. Sources are the native A04 schematics/library, the MCP-exported candidate 2 netlist and the installed KiCad 10.0.4 footprint libraries. This is an area/accounting check, not a fit or fabrication approval.

## Four contact-symbol warnings

The complete parsed `lib_symbols` entry for each contact **equals its library definition** after removing only the expected `AuraA04:` prefix from the outer symbol name. No properties, pins, graphical primitives, nested names or flags differ; even numeric-text normalization is unnecessary.

| Reference | Symbol | Native sheet | Library/cache `in_bom` | Placed `in_bom` | `on_board`, all three |
|---|---|---|---|---|---|
| J1 | DockContacts | `a04-power.kicad_sch` | no | yes | yes |
| J2 | BatteryPads | `a04-battery-thermal.kicad_sch` | no | yes | yes |
| J3 | SWDPads | `a04-radio-storage.kicad_sch` | no | yes | yes |
| J4 | MotorPads | `a04-interaction.kicad_sch` | no | yes | yes |

For comparison, U2/BQ25186DLHR matches its cache and library and has `in_bom=yes` everywhere. Contact `exclude_from_sim=no` also agrees across library/cache/instance; placed instances have `dnp=no`.

The BOM discrepancy is real, but **does not explain this ERC warning through KiCad 10.0.4's documented source path**. `ERC_TESTER::TestLibSymbolIssues()` compares a flattened library symbol against `GetLibSymbolRef()` using `EQUALITY | ERC`. It does not directly compare the placed symbol's BOM flag. [Official 10.0.4 ERC source, lines 1657–1764](https://gitlab.com/kicad/code/kicad/-/blob/10.0.4/eeschema/erc/erc.cpp#L1657).

Moreover, `LIB_SYMBOL::Compare()` puts BOM, board, simulation and position-file flag comparisons inside the branch where the ERC flag is **absent**. The BOM difference is therefore specifically skipped for this check. [Official 10.0.4 comparison source, lines 2269–2325](https://gitlab.com/kicad/code/kicad/-/blob/10.0.4/eeschema/lib_symbol.cpp#L2269). The installed executable identifies itself as 10.0.4, file version 10.0.4.50200; the candidate netlist likewise identifies Eeschema 10.0.4.

**Exact ERC cause remains unresolved.** Current serialized symbol content does not substantiate a pin/graphics mismatch, and the instance-BOM hypothesis is contradicted by the ERC comparison path. A difference in loaded/flattened internal state is possible but not demonstrated. A future native comparison report must identify the actual differing field before declaring this warning resolved. The declined `update_symbol_from_library` action was not retried or replaced. Separately, the contact instances should ultimately preserve the intended exclusion from purchased-component BOMs; copper lands are not four fitted connectors.

The parent reported the native ERC as **1 error, 9 warnings** at the preceding checkpoint; this refresh did not rerun it. Read-back of [the current candidate2 netlist](../../hardware/a04/review/a04-candidate-2.net) confirms 72 references and 239 connected endpoints, plus 35 explicitly `unconnected-...` endpoints. The [first candidate netlist](../../hardware/a04/review/a04-candidate.net) remains a prior checkpoint. The three known U1 naming mismatches remain: pin20=`PDM_CLK`, pin21=`PDM_DATA`, pin38=`SPI_SCK`; the contract requires the corresponding `_MCU` names. This audit did not change them.

## Courtyard area budget

All **72 assigned footprints / 25 distinct footprint definitions** resolve locally. Every definition has a closed front courtyard. Areas below use actual closed courtyard polygon/rectangle centerlines, including stock concave outlines, not oversized bounding boxes. This provides a lower-bound occupied-area sum for a hypothetical single-face arrangement; it ignores additional placement spacing, routing, access and maximum-body differences.

Candidate 2 changes D2 to TI `TPD1E10B06DYAR` with the MCP-authored [TI DYA footprint](../../hardware/a04/AuraA04.pretty/TI_DYA0002A_TPD1E10B06.kicad_mod). Its 2.65×1.65 mm conservative, flash-inclusive courtyard is 4.3725 mm², reducing the sum by 1.7075 mm² from the prior SOD-323 assignment. Native lands are centred at X±0.74 mm, sized 0.67×0.40 mm with 0.05 mm corner radius. C7 is now Murata `GRM188R61E475KE11D`, 4.7 µF / 25 V; its existing 0603 footprint and area are unchanged. This refresh records the authored geometry and MPN change, not a new electrical or manufacturer-pad qualification.

| Group | Count | Combined courtyard area, mm² |
|---|---:|---:|
| MDBT50Q module | 1 | 189.750 |
| NAND and NOR | 2 | 93.875 |
| Other ICs | 7 | 85.457 |
| Switches | 3 | 83.070 |
| Capacitors | 19 | 61.359 |
| Copper-contact groups | 4 | 55.497 |
| Resistors | 27 | 47.207 |
| Microphones | 2 | 25.280 |
| MOSFETs | 2 | 19.079 |
| LEDs | 3 | 12.965 |
| Diodes | 2 | 10.453 |
| **Total** | **72** | **683.992** |

The actual circular outline is Ø35.2 mm: **973.140 mm²**, so these courtyards alone consume **70.29%** of one face. The specified Ø10.1 mm maximum motor body adds at least **80.118 mm²**, bringing a non-overlapping component/motor budget to **764.110 mm² / 78.52%**, before its projecting tab, wire bends and mounting clearance. The 2.45 mm component/motor height allocation does not allow assuming the motor can simply stack on top of ordinary components. Motor dimensions and the separate height budget are sourced in the [electrical architecture](electrical-architecture.md) and [mechanical contract](industrial-design.md).

The provisional upper `Y≥9.8` RF sector occupies **160.373 mm²** of the circle, leaving **812.767 mm²** below it. Naively adding the entire sector to all courtyards and motor gives **924.483 mm² / 95.00%**, but that double-counts the module portion that will sit inside the RF reserve. It is an illustration of pressure on the layout, **not a valid union area or proof of failure**. The actual module footprint already contains a 12.4×3.75 mm all-copper-layer antenna keepout and a separate small front keepout; their transformed position and the broader mechanical exclusion must be respected.

Area alone does not rule out the disk, but it does not establish plausible routing/assembly margin for a single-face solution. Curvature, the wide switch/module, RF allocation, two acoustic channels and the motor compete for shape and perimeter access. A second assembly face is not a free doubling: the rear 26×21 mm pack envelope occupies 546 mm² and the present depth allocation leaves no ordinary component-height allowance beneath it.

## Missing definitions and obvious mechanical issues

- **No assigned PCB land file is missing.** J1/J2/J3/J4 contain actual numbered copper/mask pads and courtyards, deliberately without paste. MK1/MK2's stock footprint includes a Ø0.5 mm acoustic NPTH. This finding does not requalify any pad shape against the manufacturer drawing.
- **The motor body is not represented by J4.** J4 is only a 4.44×2.30 mm two-wire solder-land courtyard. The Ø10.1 mm motor, tab extending6.6 mm from its centre, lead channel, adhesive and mounted-height envelope need separate mechanical placement/keepouts. Dock pogo mating geometry, wire strain relief and acoustic channel/foam geometry likewise remain assembly definitions, not proven by these lands.
- **The unnotched circle conflicts with the provisional screw-boss allocation.** Boss centres are at radius17.8 mm; Ø3.6 mm bosses plus0.30 mm radial clearance require radius2.1 mm exclusion circles. Each intersects the Ø35.2 mm PCB by about **5.917 mm²**, or **11.834 mm²** total. The current board has only a circular Edge.Cuts primitive, with no negotiated notches. This follows the published provisional boss centres; actual mounting strategy still needs agreement.
- **The native board contains zero placed footprints and is still1.6 mm thick.** The0.8 mm target, final side assignments, all-layer/case RF exclusions, mounting cuts and supplier land/process checks remain open. No placement success is inferred from the courtyard sum.

Current snapshot identities: `AuraA04.kicad_sym` SHA256 `5607e9277f5bff86f87781af3fb4cf7ca46820bb50af4d6bf240392847fbb444`; `aura-a04.kicad_pcb` SHA256 `62a1492e8e55bd9f732c8d3df92cbfb227e73a31c822b8ee552886ca1debbaa5`; `a04-candidate-2.net` SHA256 `1c3c36035e4b16211a3fb2f4a8cbd5009b58d55e98f4cabe10faaa3c38a4122f`; new D2 footprint SHA256 `be78a70dd1f824e14fc2b7e5fb9fefe9ccfe2481e452b67bdc18087a5972d923`. The retained first candidate netlist has SHA256 `aa803878edc29b952dd58a99b24d015b3c57db84335137aca6980f2d46c29c1e`. Library geometry came from installed `C:/Program Files/KiCad/10.0/share/kicad/footprints`, plus the project `AuraA04.pretty` and reviewed `hardware/library.pretty` directories.
