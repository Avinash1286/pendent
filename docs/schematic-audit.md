# A03 native schematic parity and conversion audit

Audit date: 2026-09-08. The separate native reconstruction is complete. KiCad MCP created and connected the functional sheets, typed custom symbols and individual NC markers. A user-authorized source/CLI fallback corrected documented MCP presentation and metadata defects. No PCB was edited or synchronized by this schematic work, and no authored net assignment changed.

**The current native schematic passes KiCad 10.0.4 ERC with zero errors and zero warnings. Its native XML netlist exactly matches all 43 intended named nets and all 208 connected component/pin pairs.** The 968 findings described later belong to the preserved, superseded converter file `hardware/output/aura.kicad_sch`, not the current design.

## Current verified deliverables

- [Native root schematic](../hardware/output/aura-a03-electrical.kicad_sch) and five A4 landscape subsheets: `a03-radio`, `a03-audio`, `a03-storage`, `a03-charging` and `a03-controls`.
- [Six-page native schematic PDF](../hardware/output/aura-a03-native-schematic.pdf), with SVG and PNG page previews in `hardware/output/native-sheets/`. Each page was visually inspected for readable labels, component identities, sheet boundaries and title-block clearance.
- [Exact parity report](../hardware/output/native-schematic-parity.json), [native XML netlist](../hardware/output/aura-a03-native.net.xml) and [zero-finding native ERC report](../hardware/output/aura-a03-native-erc.json).
- [Repeatable verifier](../hardware/scripts/verify-native-schematic.ps1): run with `-Refresh` to regenerate native XML/ERC, then compare net membership, references, MPNs, footprint links and NCs against the authored manifest.
- [Typed custom symbol library](../hardware/library/AuraA03.kicad_sym), plus project-relative symbol and footprint tables. The custom URIs use `${KIPRJMOD}/../library/AuraA03.kicad_sym` and `${KIPRJMOD}/../library.pretty`.

| Native check | Final result |
|---|---:|
| Real component references, exactly matching manifest | 61 |
| Intended named nets, exact member-set comparison | 43 |
| Intended connected component/pin pairs | 208 |
| Intentional NC pins, exact member-set comparison | 37 |
| Individual NC markers | 37 |
| Native nets including 37 intentional unconnected records | 80 |
| Explicit external/conditional PWR_FLAG symbols | 4 |
| Blank/mismatched footprint links or MPNs | 0 |
| ERC errors / warnings | 0 / 0 |

U1 uses the installed `RF_Module:MDBT50Q-1MV2` symbol, with its 34 intentional NC pins. The other three NCs are U4.4, U7.4 and U9.1. The library contains 14 custom definitions; the unused alternate U1 specification remains in the reconstruction-input record for provenance. The four flags represent GND, external VBAT, dock power after the series diode, and the ON-state switched microphone rail. No project-specific ERC exclusions were added. KiCad's default disabled checks remain explicitly listed in the report.

## Diagnosed MCP fallback corrections

The batch connection tool initially oriented labels into component bodies. A targeted [formatter](../hardware/scripts/format-native-schematic.mjs) now orients each label outward using the actual library pin direction, places resistor/capacitor fields beside their bodies, and carries MPN/function metadata. It asserts unchanged component positions, wire endpoints, NC points, and label name/anchor sets before writing. MCP moved the few bottom-row components that otherwise touched the A4 title block; their attached labels followed. Native XML parity was rerun after these changes.

Four custom-contact library warnings had a specific version-conversion cause. MCP wrote the library as version `20241209` with `Datasheet "~"` to mean an empty field, then copied that same text into version `20260101` schematic caches where the tilde is literal. KiCad's native `sym upgrade` diagnostic export changed exactly those four property values from `"~"` to `""`. The [KiCad parser source](https://docs.kicad.org/doxygen/sch__io__kicad__sexpr__parser_8cpp_source.html) documents the legacy empty-tilde conversion for pre-20250318 files. Normalizing only J1–J4's empty datasheet fields in the library and caches removed all four warnings. Pin numbers, electrical types, graphics and net memberships were unchanged.

The `.kicad_pro` alongside the new root enables CLI project-library resolution. The board is maintained separately because a schematic-to-board synchronization must explicitly reconcile its original footprint UUIDs and the new schematic instances; no such synchronization was performed here.

The following sections retain the original conversion diagnosis and the reconstruction approach for traceability.

## Verified scope and counts

Inputs: `hardware/output/aura.kicad_sch`, `hardware/output/kicad-a03-schematic-erc.json`, `hardware/output/aura-placement.circuit.json`, `hardware/output/logical-netlist.json`, `hardware/output/design-manifest.json`, `hardware/src/design.ts`, and `hardware/scripts/export.mjs`.

The primary authored design has 61 real references, 43 named nets, 208 connected logical component/pin pairs, and 37 intentional unconnected pins. The separate PCB export verification covers those 208 assignments; it does not establish native schematic connectivity.

Read-only `generate_netlist` on `aura.kicad_sch` returned **268 native nets**. They consist of 48 two-pin islands and 220 singleton nets. The singleton nets contain 149 real component pins and 71 false rail-component pins. Of the 149 real singletons, 37 are intentional NCs and **112 should be wired into named nets**.

| ERC class | Count | Interpretation |
|---|---:|---|
| `pin_not_connected` | 220 | 112 intended wired pins + 37 intentional NCs without X markers + 71 false rail pins |
| `endpoint_off_grid` | 494 | Exported 3 mm pin pitch and arbitrary fractional origins are incompatible with the default 1.27 mm connection grid |
| `lib_symbol_issues` | 132 | 61 generated `Device:U_*` instances whose definitions are not in Device + 71 unregistered Custom rail instances |
| `unconnected_wire_endpoint` | 122 | Stubs and rail branches left without actual electrical labels/end connections |

The native file has 132 placed symbol instances, 89 graphical texts, 18 junctions, and 362 wires. It contains **zero local labels, zero global labels, and zero no-connect markers**. The netlist tool reports 68 unique component reference strings because the 71 false rail instances reuse seven strings: GND, V3, VBAT, VSYS, MIC_VDD, DOCK_5V, and CHG_VSET.

## Exact conversion defects

### Signal names become drawings, not net labels

The tscircuit JSON represents 89 non-power net names as `schematic_text` records linked to `source_trace_id`. The bundled `circuit-json-to-kicad` converter's `AddSchematicGraphicsStage` exports these as KiCad `(text ...)` graphics. It never creates electrical labels from their source-trace connection semantics.

For example, authored `source_trace_3` connects U1 pin 16 to I2C_SCL. Its schematic wire runs from source coordinate (-3.9, 0) to (-4.74, 0), and its displayed `schematic_text_122` says I2C_SCL. After conversion, read-only MCP reports U1 pin 16 at **(-914.7925, -295.15) mm**. The wire touches that pin but ends without an electrical label; I2C_SCL text is only a drawing. The native netlist calls it `unconnected-(U1-P027_SCL-Pad16)`, separate from U5.7, U6.2, and R6.1.

The source-to-native transformation is consistent for this real pin and wire. A generic pin-offset correction would not restore the missing net name.

Relevant installed converter code: `hardware/node_modules/@tscircuit/cli/dist/cli/main.js`, `AddSchematicGraphicsStage` at lines 142955–143028, especially creation of `SchematicText` at 143018.

### Rail symbols are electrically wrong and displaced

All 71 `schematic_net_label` records have `symbol_name` (rail_up or rail_down). `AddSchematicNetLabelsStage` therefore instantiates them as ordinary symbols, with `inBom:true`, `onBoard:true`, and Reference equal to the net name. The generated rail library has a passive pin named `1`, lacks power-symbol semantics, and consequently does not join instances sharing a visible rail name.

It also puts the symbol origin at the intended connection anchor without compensating the symbol's pin offset. The first GND branch should join at **(-917.7925, -334.15) mm**. Its rail_down library pin is at local (0, +1.35), so its actual connection point is **(-917.7925, -335.50) mm**: 1.35 mm away from the wire anchor. Connecting the displaced rail pin alone would still not merge the rail by name.

Relevant converter code: `createLibrarySymbolForNetLabel` at 142819; `createLibrarySymbol` at 142849; `createSymbolFromNetLabel` at 143076. The latter explicitly sets the normal-component and repeated-reference properties.

### Intentional NCs and footprint links are omitted

The original TSX marks U1's 34 unused pins, U4.4, U7.4, and U9.1 as NC in its declarative part definitions. No native `(no_connect ...)` records are exported. They should receive individual X markers; suppressing all `pin_not_connected` findings would hide the 112 real failures.

All 61 real schematic instances have a blank Footprint field, even when the embedded library definition names `tscircuit:<MPN>`. The converter reads instance footprint only from optional schematic-symbol metadata and defaults to an empty string (`AddSchematicSymbolsStage`, 143294–143300). Restoring the instance footprint must use the **existing board's exact footprint identifier**, including the corrected microphone annulus and SiCap lands, not substitute an older library geometry.

### Scale, sheet extent and electrical types need reconstruction

The converter applies a fixed factor of 15. Authored pin pitch 0.2 becomes 3 mm. Real wire bounds are approximately **X -933.4075 to +2122.4075 mm; Y -340.15 to +1184.15 mm**, larger than the selected A0 page and partly outside its origin. Translating symbols alone will not put both 3 mm-spaced pins on a 1.27 mm grid. Snap or regenerate the symbol geometry and then reconnect by pin identity.

The stored ERC JSON's `pos` values are 100 times smaller than the native file and MCP pin coordinates (for example U1.3 reports -9.147925/-3.3415 versus actual -914.7925/-334.15 mm). The cause of this report-unit discrepancy was not established; it is not evidence that the actual schematic needs another factor of 100. Use native MCP pin positions for mutations.

All generated real pin definitions are passive, so this ERC run cannot check meaningful power direction, input/output or driver conflicts. New typed symbols should represent actual device functions. Intentional passive terminal choices must be documented individually.

## Prepared native reconstruction data

[native-symbol-specs.json](../hardware/scripts/native-symbol-specs.json) is declarative input data; it is not a KiCad file. It provides:

- 15 `create_symbol` argument objects for 17 custom references, covering U1–U9, Q1, SW1, MK1/MK2 and J1–J4. U4/U7 share one definition; both microphones share one definition.
- All 61 instance symbol IDs, exact existing-board footprint IDs, values, metadata and numeric pin-to-net assignments.
- The 37 exact NC marker requests, without changing or removing any authored connection.
- 2.54 mm pin pitch and coordinates compatible with a 1.27 mm connection grid.
- Individual justifications for pin types and conditional external-source power flags.

The generated data was checked against the existing logical netlist: **43 net names and all 208 component.pin sets match exactly**. Custom symbol pin sets equal connected pins plus the existing NC lists. The completed native implementation and its verification are reported above; the original data remains a reconstruction-input record rather than the final instance-library inventory.

Particularly important types are:

| Part/pin | Proposed type | Reason |
|---|---|---|
| U1 GPIO / SWDIO | bidirectional | Actual configurable digital pad roles; firmware direction remains a separate check |
| U1.31 DCCH / U1.53 SWDCLK | power_out / input | Real DC/DC output deliberately open; debugger clock input |
| U1.46 P0.22 | bidirectional + NC marker | An unused GPIO, not a physically unconnected module pad |
| U3.1 SYS / U3.2 BAT | power_out / passive | SYS drives loads; BAT is a bidirectional power terminal, for which KiCad has no dedicated type |
| U3 STAT1/STAT2, U5 ALRT, U9 outputs | open_collector | KiCad representation of open-drain outputs |
| U5.2 CELL | passive | MAX17048 has no internal connection here, but its datasheet explicitly directs connection to battery positive |
| MK1/MK2 DATA | tri_state | Correct for alternate half-cycle PDM data multiplexing; avoids falsely modeling two simultaneous push-pull drivers |
| U8.3/U8.6 | tri_state | Actual three-state buffer outputs with Ioff behavior |
| Q1 source/drain | passive | Switch terminals; body-diode source-to-drain orientation needs graphical and electrical review |

The local KiCad 10 libraries were read to verify standard symbols: Device:R and Device:C have passive pins 1/2; Device:LED and Device:D_Schottky use 1 cathode and 2 anode; Device:D_TVS uses passive A1/A2; Switch:SW_Push uses contact pins 1/2. SW1 needs its explicit custom numbering because commons are pins 2 and 5.

## Reconstruction approach retained for traceability

1. Preserve the original interchange file and reports as evidence. Create a separate `aura-a03-native.kicad_sch` using `create_schematic` in the already-open project; do not synchronize the malformed original.
2. Pass each prepared `createSymbol` object to `create_symbol`, then register AuraA03 in the project with `register_symbol_library`. Re-read a representative library with `list_symbol_pins`, especially U1, U3, U5, Q1 and SW1.
3. Place functional blocks on a 1.27 mm grid using `batch_add_and_connect`. Supply the prepared numeric `nets` maps and explicit `labelType:"global_label"` so connections do not depend on nearby-label heuristics. Populate Footprint on every real instance and preserve MPN metadata.
4. Add only the 37 specified X markers using `batch_add_no_connects`. Do not mark supply pins or intended wired pins NC to satisfy ERC.
5. Add PWR_FLAG only where the documented external or conditional power path requires it. Review GND, DOCK_5V, DOCK_IN after the passive diode, VBAT at the external battery, and MIC_VDD after SW1. The MIC_VDD flag represents an ON-state power source and is not proof that this switched rail is always energized.
6. Use `get_schematic_pin_locations`, `generate_netlist`, `run_erc`, and schematic SVG/PDF export to verify. Require exactly the same 43 named connected-net memberships and 208 component.pin assignments, no ghost rail references, no missing footprint fields, and exactly the authored intentional NCs. Check every additional ERC warning on its facts.
7. Before any `sync_schematic_to_board`, reconcile existing footprint UUIDs/reference association and verify the registered footprint library actually resolves to the corrected existing board geometry. An automatic sync can duplicate or replace footprints when schematic instance UUIDs differ. Test this only on an intentional board copy and compare all 61 placements, 208 assignments, keepouts and copper. Never replace the preserved board with an unchecked sync result.

## Source evidence

Electrical roles were checked against the current part map, the installed KiCad 10 symbols, and manufacturer documentation. Raytac's Version L PDF was fetched and read in memory after the browser PDF fetch timed out; it was not saved or redistributed. Other retrieved sources include [TI BQ25185 Rev B](https://www.ti.com/lit/ds/symlink/bq25185.pdf), [TI DRV2605L Rev D](https://www.ti.com/lit/ds/symlink/drv2605l.pdf), [TI SN74LVC2G125](https://www.ti.com/lit/ds/symlink/sn74lvc2g125.pdf), [TI TLV6700](https://www.ti.com/lit/ds/symlink/tlv6700.pdf), [TI TLV755P](https://www.ti.com/lit/ds/symlink/tlv755p.pdf), [ADI MAX17048/49](https://www.analog.com/media/en/technical-documentation/data-sheets/max17048-max17049.pdf), [Diodes DMG2302UK](https://www.diodes.com/datasheet/download/DMG2302UK.pdf), and [Knowles SPH0641LU4H-1 manufacturer PDF](https://xonstorage.z8.web.core.windows.net/pdf/knowles_sph0641lu4h1_apr22_xonlink.pdf). The previously reviewed Winbond ZE package mapping is preserved without modification.

This work establishes native schematic reconstruction, exact logical parity and clean native ERC. It does not establish PCB DRC results, fabrication readiness or battery/RF/thermal qualification. Firmware security, audio reliability, NAND management, charging behavior and physical tests remain separate validation work.
