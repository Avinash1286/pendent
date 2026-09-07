# AURA — product design specification

## Product definition

A necklace voice recorder that lets someone capture a thought without retrieving a phone. Its intended companion app produces transcripts, summaries and actionable notes after transfer. This repository contains the design and presentation assets; it does not contain a complete mobile app, deployed AI backend or tested device firmware.

The primary product promise is **Be here. Keep the thought.** AI is useful only after reliable, legible recording. The pendant has no display, camera, speaker or always-listening wake word. These choices reduce interaction, battery and privacy costs.

## Physical design

Revision A02 targets a 40mm tall ×30mm wide ×9.5mm deep body. A low-profile integrated bail extends the case height to 42.8mm. The PCB envelope is 24mm ×34mm ×0.8mm with R4 corners. The industrial design uses an RF-transparent polymer body with a satin ceramic / titanium-color finish; it is not a solid titanium shell. Lunar, Graphite and Dune are proposed colorways. A01 is preserved in the enclosure and film archives.

The case separates into front and rear shells. A flush button with integral plunger, separate board retainer, threaded fasteners, acoustic passages and a physical switch opening are represented in the Blender design. Separate printable meshes and a fit coupon support assembly trials. Tough resin printing is the intended prototype process; mesh manifoldness alone does not establish tolerances, fastening strength or acoustic performance. See the mechanical guide for actual clearances, orientations and support placement.

An adjustable cord should have a tested breakaway clasp. Do not infer tensile or release-force certification from the visualization. The magnetic charging dock is an accessory concept; electrical charging contacts are included in the board and case work, but a complete dock production design is not supplied.

## Interaction contract for future firmware

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

These are requirements, not implemented behaviors. Gesture thresholds, error patterns and debounce timing need usability tests. The recording indicator is intentionally visible to bystanders. The circuit's available indication must be checked against firmware logic before claiming it means “audio is safely stored.”

## Audio and note pipeline

1. Two microphones feed the MCU's digital audio interface. Acoustic seals keep enclosure cavity resonance out of the microphone path. Clothing rub, wind, speaker distance and placement require physical tests.
2. Firmware writes timestamped, recoverable audio chunks to local flash. Compression, mono/stereo policy and sample rate are to be selected through measured intelligibility and energy tests. Capacity must be stated only for the implemented codec and usable flash size.
3. An authenticated companion connection requests a manifest and missing chunks. Device chunks are deleted only after checksum verification and explicit retention policy confirmation.
4. The app presents a local recording first. AI processing is opt-in, with a clear indication of which recordings leave the phone and for how long they are retained.
5. Transcription preserves uncertainty and speaker ambiguity. A summary links back to timestamped audio. Suggested tasks and dates remain editable; no tasks, messages or calendar entries are sent automatically.
6. Search indexes user-approved notes. Export includes plain text, Markdown and original audio. Delete removes derived embeddings and remote copies according to the selected service policy.

The architecture needs signed firmware updates, secure pairing, at-rest encryption with a documented key lifecycle, authenticated transfer and a consent-aware app. These are outstanding implementation requirements, not verified security properties.

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

