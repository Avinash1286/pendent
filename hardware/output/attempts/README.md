# Historical routing and conversion attempts

These files are retained to make the engineering history reproducible. None is a manufacturing release or a valid final A03 routed board.

- `krt-failed*` and the routing-attempt Circuit JSON contain a failed KRT run: zero copper and 199 disconnected-port findings. They must not be treated as a routed PCB.
- `pre-a03/aura-a02-route.ses` contains 372 wire paths and 82 vias, with 24 connections remaining in that router run. It predates the corrected 8 × 6 mm NAND footprint and the A03 board/thermal design. It is not compatible with the current board.
- `pre-a03/aura-a02-routing-draft.kicad_pcb` was a copied placement board intended for import. The connector declined SES import before execution, so this file contains no imported routed copper despite its historical filename.
- Wedge-baseline sessions use an earlier microphone representation; later placement reports restore the native annulus and compensate for footprint-origin shifts.
- Old DRC reports document their own exact inputs. Do not combine a former error count with a newer board or routing session.
- `never-executed-finish-kicad.mjs.txt` is an abandoned metadata-cleanup sketch. It was never run and is not part of the build or permitted routing-import workflow. The `.txt` suffix is intentional.
- `obsolete-solid-microphone-footprint.tsx.txt` records the initial converter output that incorrectly filled the acoustic ground ring. It is not imported by the current source.

Current authoritative inputs are the A03 source, manifest, placement export and input hashes one directory above. A final manufacturing release requires matching routing input, successful import and independent routed-board DRC/connectivity.
