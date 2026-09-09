# A04 assembly attributes review

Read-only native audit, 2026-09-09. **Seven references need assembly-attribute corrections before manufacturing exports:** D2/C3/C4 lack the footprint-level SMD classification, and J1–J4 copper contact features remain included in BOM/position intent. The current design has **72 assigned PCB references, comprising 68 purchased PCB components and four copper-contact features**. It is not ready for an assembly release.

[The reproducible audit](audit-assembly-attributes.py) reads the candidate 2 netlist, all seven native schematic files, the actual assigned footprint files and the native board. KiCad `pcbnew` 10.0.4 parses the 25 assigned footprint definitions and board; a structural S-expression parser distinguishes schematic instances from cached library symbols. [The JSON evidence](assembly-attributes-verification.json) records each reference, definition, native flags and SHA256 identities. All 38 recorded source files remained unchanged during execution. The script writes only that JSON; its successful exit means the audit completed consistently, not that the attribute policy passed. `assembly_attribute_policy_pass` is **false**.

| References | Actual native footprint attributes | Native paste geometry | Assembly implication |
|---|---|---|---|
| D2 — `AuraA04:TI_DYA0002A_TPD1E10B06` | `0`: neither SMD nor through-hole; no position/BOM exclusions | Two front-paste pads | Purchased SMD diode can be omitted by the SMD-only placement filter |
| C3, C4 — `AuraVerified:AURA_SiCap_1.2x0.7mm_P0.7mm` | `0`: neither SMD nor through-hole; no position/BOM exclusions | Two front-paste pads per definition | Purchased silicon capacitors can be omitted by the same filter |
| J1, J2, J3, J4 — DockContacts, BatteryPads, SWDPads, MotorPads | `0`; no position/BOM exclusions | No paste pads or paste graphics | Unfiltered component lists can include four fictitious connector purchases/placements |
| Remaining 65 purchased references / 19 definitions | `2`: `FP_SMD` set | Recorded per definition in JSON | SMD classification is present; this is not an orientation or process qualification |

Pad-level `smd` geometry does not set the footprint-level `FP_SMD` bit. KiCad's SMD-only position filter uses the footprint fabrication attribute, while the position exclusion flag suppresses a footprint independently. This makes omission of D2/C3/C4 a prediction **if these library attributes reach placed board instances**, not a verified CPL export result. [KiCad 10 PCB Editor manual, component placement files](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.pdf)

All 72 native schematic instances explicitly have `in_bom=yes`, `on_board=yes`, `in_pos_files=yes`, `dnp=no`. J1–J4's library and cached symbols say `in_bom=no`, but their placed schematic instances override that intent to `yes`. Those four references must retain their PCB copper and `on_board=yes`, while component BOM and position exclusions must be made explicit and preserved through schematic-to-board synchronization. Their labels describe lands, not four procured connectors. The actual motor, protected battery pack, mating dock and programming-fixture hardware require separate product/fixture BOM accounting.

The native board still contains **zero footprints** and has **1.6 mm thickness**. No placement file or BOM was exported or inspected by this audit; no placement, side, rotation, stackup, solder-process, electrical or enclosure-fit approval follows. `AuraA04:Nidec_CUS22TB_Candidate` is **unassigned and excluded from the 72-reference count**, with its own [separate candidate review](cus22-candidate-review.md).

The exposed MCP schemas provide a supported future board-instance correction: `set_footprint_type` accepts a placed PCB reference, `type` (`smd`, `through_hole` or `unspecified`), and optional `exclude_from_bom` and `exclude_from_pos_files`. The separate `create_footprint` and `edit_footprint_pad` schemas do not expose a **library footprint-level** attribute setter. This audit only inspected those tool descriptions; it made no MCP calls or CAD edits. Native library correction therefore remains a separate capability question; direct file patching is not a substitute in this workflow.

After the 72 references are placed through the authorized native workflow, set/read back D2/C3/C4 as SMD and J1–J4 as excluded from component BOM/position files while retaining their copper features. Verify the saved board instances after schematic synchronization and library refresh. Then compare actual BOM and CPL reference sets against the intended **68 purchased PCB references**; confirm D2/C3/C4 are present, J1–J4 absent, and all expected quantities, sides, rotations and origins match the assembler's requirements. This must use real exported files, not the current library-derived count.

To reproduce from the repository root in PowerShell:

```powershell
& 'C:/Program Files/KiCad/10.0/bin/python.exe' 'docs/a04/audit-assembly-attributes.py'
```

The optional `--stock-library-root` accepts a different installed KiCad footprint directory. Repository source keys use relative slash paths; `kicad_stock/` keys are relative to the reported stock-library root. Actual footprint bytes are hashed, so another installation can identify any source differences before relying on the result.
