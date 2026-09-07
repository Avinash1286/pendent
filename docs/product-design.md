# AURA — product design specification

## Product definition

A necklace voice recorder that lets someone capture a thought without retrieving a phone. The repository now includes compiled Zephyr firmware, a Python Bluetooth/local-transcription companion, and a Next.js/Convex notes portal alongside the product design. Firmware has not run on an assembled AURA; a mobile app and production cloud deployment remain outstanding.

The primary product promise is **Be here. Keep the thought.** AI is useful only after reliable, legible recording. The pendant has no display, camera, speaker or always-listening wake word. These choices reduce interaction, battery and privacy costs.

## Physical design

Revision A03 targets a 48mm tall ×28mm wide ×10mm deep capsule body, approximately 54mm tall including the integrated bail. The PCB envelope is 24mm ×42mm ×0.8mm with R10 corners. A glossy black recording face sits within a soft satin surround. The frame uses RF-transparent polymer with a nonconductive silver-color finish; it is not a solid metal shell. Lunar, Graphite and Dune are proposed frame finishes. Earlier revisions are preserved in the enclosure and film archives.

The case separates into frame, moving black face and rear shell. The whole face acts as a short-travel record paddle over the PCB tactile switch; it has mechanical travel stops and an underside plunger. A separate board retainer, threaded fasteners, acoustic passages and side privacy-slider opening support assembly. Separate printable meshes and a fit coupon support trials. Tough resin printing is the intended prototype process; mesh manifoldness alone does not establish tolerances, fastening strength or acoustic performance. The 10mm depth allows a printable face and 0.35mm paddle travel, with a 0.02mm nominal resting plunger gap. See the mechanical guide for actual clearances, orientations and support placement.

A fine chain or alternative cord should use a tested breakaway clasp. Do not infer tensile or release-force certification from the visualization. A conductive chain also needs antenna tests in its actual wearing position. The magnetic charging dock is an accessory concept; electrical charging contacts are included in the board and case work, but a complete dock production design is not supplied.

## Interaction contract and implementation

| State / action | Intended response |
| --- | --- |
| Privacy switch OFF | Microphone rail physically disconnected. UI must say recording unavailable. No software override. |
| Privacy ON, idle: short press | Begin recording after storage and supply checks. One brief haptic pulse; steady visible recording light. |
| Recording: short press | Commit and close audio segment. Two short haptic pulses; light goes out after the save succeeds. |
| Recording: double press | Add a timestamp bookmark, confirmed with a distinct brief haptic pattern. Firmware must defer stop until the double-press interval expires. |
| Idle: hold 3seconds | Enter time-limited pairing, if microphone switch is on. Slow indicator pulse. Require physical confirmation for a new phone. |
| Storage full / unsafe voltage | Do not silently discard old recordings. Reject a new recording with an unmistakable error pattern; explain the issue in the app. |
| Privacy moved OFF while recording | Immediate hardware microphone disconnect. Firmware closes the existing file and marks its ending as privacy stopped. |
| Phone unavailable | Keep recording locally. Resume a bounded, checksum-verified transfer later. |
| Power loss during recording | Recover completed journaled audio chunks on the next boot. Mark a partial last chunk, never invent audio. |
| Charging | Prioritize cell temperature and charger state. Confirm charge through the app; distinguish charging feedback from the recording indication. |

These are product requirements; the firmware guide identifies the implemented subset precisely. Recording, bookmarking, pairing, privacy gating, recoverable storage and guarded transfer are implemented in the compiled code. The distributed image disables charging and haptics pending physical qualification. The amber light indicates microphone power, not proof that audio was safely stored; separate pairing/error light patterns are not implemented. Bookmarks are journaled but not yet exported by protocol v1. Gesture thresholds need usability tests.

## Audio and note pipeline

1. Two microphones feed the MCU's digital audio interface. Acoustic seals keep enclosure cavity resonance out of the microphone path. Clothing rub, wind, speaker distance and placement require physical tests.
2. Firmware mixes two PDM channels to mono 16kHz PCM16 and writes recoverable journaled NAND pages. The ideal storage bound is about 66 minutes before metadata, bad blocks and reserves. Battery runtime has not been measured.
3. An authenticated companion connection requests a manifest and missing chunks. Device chunks are deleted only after checksum verification and explicit retention policy confirmation.
4. The Python companion saves a verified local WAV and runs Whisper locally. Optional local Ollama summaries and explicit transcript upload are available. Audio is not uploaded by the portal integration.
5. Transcription preserves uncertainty and speaker ambiguity. A summary links back to timestamped audio. Suggested tasks and dates remain editable; no tasks, messages or calendar entries are sent automatically.
6. The Next.js/Convex portal stores searchable transcripts and editable notes. Selected notes and personal goals become a reviewed Markdown Context Pack for any AI chat. A revocable read-only MCP endpoint exposes only approved live notes. Archiving is reversible and excludes a note from live context. Account deletion and remote hard-delete workflows remain future work; no embeddings are created.

Encrypted BLE transfer and physical pairing windows are implemented. Just Works pairing is not authenticated MITM protection. Signed firmware updates, at-rest encryption, key provisioning and physical extraction resistance remain outstanding. The portal enforces owner boundaries and scoped tokens; it is not end-to-end encrypted.

## Battery and thermal UX

Use a protected, traceable cell that physically fits the validated pouch envelope. Charging must honor the cell supplier's current, temperature and voltage limits, including NTC calibration and charger tolerance. The hardware documentation contains the actual selected power architecture. Any battery-life figure must be measured on firmware running real audio and BLE workloads. This presentation deliberately makes no runtime, charge-time, waterproofing or weight claim.

## Website and launch film

The website uses the actual Blender GLB, local product renders and a local Manrope font. Visitors can rotate the model, select physical parts, change the camera angle, see through the shell and continuously scrub or play the assembly. A separate finish configurator, sample recording-to-note sequence, 36second film and downloadable design configuration complete the presentation. The AI example is fixed sample content; it never requests microphone access. A saved configuration is not an order or a reservation.

The proposed 179USD price is a design target, not a validated landed cost or sales offer. No merchant credentials, inventory, payment endpoint or shipping promises are present. Sale should open only after engineering validation, manufacturing quotes, business details and an authorized payment account are established.

## Release evidence required

- Electrical review against current manufacturer datasheets; independent ERC/DRC and fabrication-file review.
- Prototype bring-up: current-limited power, rails, flash, microphone isolation and charging with the selected cell.
- Battery abuse / temperature assessment by an appropriate lab; RF compliance and antenna testing in the final enclosure.
- Audio tests in quiet rooms, street noise, wind and against clothing; bystander clarity of the recording indicator.
- Fit prints with the real populated board, cell, gasket, fasteners and cord.
- Companion and firmware implementation, recovery / retention tests, security review and accessibility/usability trials.

See the hardware and enclosure validation reports for what was actually checked in this delivery.

