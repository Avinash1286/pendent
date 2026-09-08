# AURA A04 — fresh KiCad MCP project

Status: **incomplete engineering design, not a fabrication release**. This project starts from a new native KiCad project, schematic hierarchy and board; it does not import the routed A03 board as a template. All new CAD mutations are made through KiCad MCP. Existing exact-MPN library definitions may be consulted or reused after verification.

The [full A04 objective](../../docs/a04/requirements.md) includes the circular pendant, real manufacturing and printable-part checks, firmware, mobile/context workflow, website, film and physical launch qualification. These files are one workstream toward that objective.

## Native state

- `aura-a04.kicad_pro`, `aura-a04.kicad_sch` and `aura-a04.kicad_pcb` are the new project.
- Three primary subsheets separate power/charging, radio/storage and microphones/controls, with three nested sheets for battery/thermal sensing, NAND and interaction.
- The initial circular outline is Ø35.2 mm at native datum (100,100) mm, with four copper layers. Its native thickness is currently **1.6 mm**. The mechanical 0.8 mm target has not been applied.
- The schematic contains all **72 candidate PCB references** and is checked against **239 intended connected endpoints**. Three MCU net names still differ from the contract; the schematic is incomplete. The PCB has no imported components, placement, tracks or zones yet. Do not interpret an empty-board check as design verification.
- `AuraA04.kicad_sym` contains the MCP-authored BQ25186DLHR symbol, with eleven physical pads checked against TI SLUSF69A, plus four copper-contact symbols. `AuraA04.pretty` holds their newly authored contact footprints. See the [pin evidence](../../docs/a04/pin-definitions.json).
- `review/schematic/` contains an MCP export of a work-in-progress schematic, not an approved drawing.
- [The seven-page candidate PDF](review/a04-schematic-candidate.pdf) is the current complete-sheet export; `review/a04-candidate-2.net` is the current MCP XML netlist. Earlier small SVG exports are retained as development snapshots.

The separately authored [CUS-22TB candidate footprint](AuraA04.pretty/Nidec_CUS22TB_Candidate.kicad_mod) is **unassigned**. Its ten numbered lands and two locating holes were created through MCP and inspected with KiCad's native parser. [The review and M1 errata](../../docs/a04/cus22-candidate-review.md) document the proposed underside orientation, actuator offset, ground-tab uncertainty and an old mounting-notch collision. Native SW1 remains JS202011JCQN; candidate creation does not establish substitution, placement or fabrication readiness.

## Checks and unresolved tooling

KiCad declined `set_design_rules` twice with `cancelled: true`, `action: decline` and no reason. The second request only tightened clearance and courtyard checking. Neither request was executed; no alias, file patch or approval-setting change was used to bypass the decline. Routing is not authorized by a presumed rule set. The available MCP metadata exposes no board-thickness or dielectric-stackup setter.

During visual cleanup, `delete_schematic_net_label` was also declined. The first cleanup loop checked only the outer MCP error flag and missed the nested cancellation, then added outward-facing labels. The exported power sheet revealed eleven duplicate label pairs at U2. An inspected single-operation response confirmed the decline. These same-net duplicates and the inward-facing labels must be resolved before drawing approval; the loop was stopped and no equivalent deletion path was used. Subsequent operations inspect nested `success`/`cancelled` results as well as the outer error flag.

`update_symbol_from_library` was declined once as well, leaving four contact-symbol library mismatch warnings unresolved. These tool responses give no reason; they are recorded as unresolved operations, not proof that a particular approval policy rejected the design. Existing CAD was not patched through another route.

Project symbol registration currently writes **absolute local library URIs**. Embedded schematic symbols remain in the native schematic, but the library table is not yet a portable release configuration. On another machine, the corresponding libraries must be registered through KiCad MCP with that checkout's actual paths. Do not assume this work-in-progress table resolves unchanged after cloning.

The current native ERC reports **one error and nine warnings**, independently reproduced by KiCad CLI 10.0.4. [The raw report](../../docs/a04/native-erc.json) retains all findings. [The read-only capture audit](../../docs/a04/audit-native-capture.py) compares the MCP-exported XML netlist to the design contract and deliberately returns nonzero for the three net mismatches and eleven duplicate label positions. [Its report](../../docs/a04/native-capture-verification.json) binds those findings to source hashes. Intentional unused pins have explicit no-connect markers; power flags identify actual external or switched supply paths, not invented drivers for signal errors.

There is no DRC, assembly-clearance, copper/paste/drill, populated-board fit or supplier CAM sign-off. There are no A04 fabrication Gerbers or a manufacturing ZIP. The earlier A03 release remains separate.

Visual inspection of the candidate PDF also found reference/value text close to some symbol boundaries and long LED labels entering the interaction sheet's title area. Drawing layout cleanup remains part of the schematic gate. The current geometrical checks do not imply a professional final drawing or an assembled fit.

Before manufacturing: complete exact-part selection and schematic review, establish valid rules and actual stackup, verify footprint pads/courtyards/tolerances, import and place the circuit, route and inspect all nets, check real populated geometry against the case, then obtain the required qualified battery/RF review and supplier/first-article evidence. A successful export alone is not fabrication readiness.
