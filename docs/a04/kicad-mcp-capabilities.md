# KiCad MCP capability and decline inspection

Read-only inspection on 2026-09-09. Scope: the metadata of all **219 currently exposed `mcp__kicad__*` tools**, the installed engineering skill, official KiCad/MCP documentation, and a narrowly filtered documented server log. No CAD mutation, project/session switch, retry of a declined operation, alias substitution, approval-setting change or security-setting change was performed for this inspection.

## Native board thickness and stackup

The live tool schemas do not expose a board-thickness or dielectric-stackup setter:

| Exposed tool | Relevant accepted fields | Capability limit |
|---|---|---|
| `create_project` | `name`, `path` | No thickness, stackup or template parameter |
| `set_board_size` | `width`, `height`, `unit` | In-plane dimensions only |
| `add_layer` | `name`, `number`, `position`, `type` | Layer identity/count; no dielectric/copper thickness or material |
| `set_design_rules` | Clearances, track/via/hole dimensions, courtyard settings | No native board thickness or stackup fields |
| `set_layer_constraints` | Layer-specific minimum track/clearance/via dimensions | Routing constraints, not physical dielectric stackup |

Native KiCad 10 supports **Board Setup → Physical Stackup** and **Adjust Dielectric Thickness**. The overall thickness follows the physical layer table and affects 3D export and via-length calculations. That native UI capability does not establish an exposed MCP operation. [Official KiCad PCB manual](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#_physical_stackup)

The current MCP-only workflow therefore has a capability gap for the required A04 0.8 mm stackup. A text annotation, requested order thickness or board outline is not a native stackup edit. The gap must be resolved through an authorized, supported MCP capability with read-back and export verification; it must not be concealed by claiming a default board has the target thickness. This inspection neither modifies the plugin nor proposes routing the previously declined design-rule mutation through a different tool.

## Portable symbol libraries

The exposed `register_symbol_library` schema accepts `libraryPath`, `libraryName`, `description`, `scope`, and `projectPath`. Its documentation calls `libraryPath` a **full path** and says project scope writes `sym-lib-table` beside the project. It neither exposes a separate portable URI argument nor promises to rewrite the full path to `${KIPRJMOD}`. [Official MCP symbol-creator guide](https://github.com/Avinash1286/KiCAD-MCP-Server-THEAVI/blob/main/docs/FOOTPRINT_SYMBOL_CREATOR_GUIDE.md#register_symbol_library)

KiCad itself accepts relative paths and `${KIPRJMOD}` in library tables. `${KIPRJMOD}` resolves to the current project directory, allowing project libraries to move with their project. [Official KiCad schematic manual](https://docs.kicad.org/10.0/en/eeschema/eeschema.html#_path_variable_substitution)

Consequently, project scope is supported, while **portable URI generation by this MCP is unproven from its documented contract**. Inspect the resulting table after the normal authorized registration and verify the project from a relocated copy before publishing a portable package. Passing an undocumented path placeholder is not established as a supported fix, and a global-library registration would not prove portability.

## Declined design-rule operation

The root agent reported two `set_design_rules` calls returning cancellation/action-decline results without a stated reason, including a call that only tightened clearance/courtyard requirements. These results were not retried during this investigation. Tool argument validity and stricter electrical limits do not reveal why a caller-side approval was declined.

No approval-history, decline-reason or cancellation-log retrieval tool appears among the 219 exposed KiCad tool schemas. `get_backend_state` is described as returning backend/realtime/project/board/dirty state; its contract does not include approval decisions. No shared MCP call was made merely to seek an undocumented approval field.

The official platform guide documents the Windows server-log location as the user's `.kicad-mcp/logs/kicad-mcp-*.log` directory. [Official MCP debugging guide](https://github.com/Avinash1286/KiCAD-MCP-Server-THEAVI/blob/main/docs/PLATFORM_GUIDE.md#testing-and-debugging)

Observed diagnostic evidence:

| Item | Result |
|---|---|
| Latest documented server-log filename | `kicad-mcp-2026-09-08.log` |
| Timestamp range observed | `2026-09-08 10:32:13` through `2026-09-09 01:42:42` as written in the log |
| Narrow case-insensitive search | `set_design_rules`, `cancelled`, `decline` |
| Matching log lines | **0** |
| Caller approval rejection reason found | **No** |

The log was live and growing during inspection. Only filenames, times, length and narrowly matched lines were considered; no full log was copied into the repository. An absent match does not prove that the server received the request, that a particular approval policy rejected it, or that the design-rule values were invalid. **The decline cause remains unknown.** Broader settings changes, server restarts, retries or equivalent mutations are not justified by this evidence.
