# A03 context and assembly film — final verification

Completed 8 September 2026 (Asia/Katmandu).

## Final artifact

- File: `../renders/aura-launch.mp4`
- Primary line, exactly: **Capture the context of your life.**
- Renderer: **Hyperframes 0.8.31**, high quality, one worker, hardware browser capture.
- Duration: **44.000000 seconds**.
- Picture: **1920×1080, 30 fps, 1,320 H.264 frames**.
- Audio: **AAC, 48 kHz, stereo**.
- Size: **13,450,756 bytes** (12.8 MiB).
- SHA-256: `3933E311B8F7E5342DBD217942B4D1433572CB25C36942A5BD9960E7CBF81738`.
- Successful render time: **2 minutes 54.5 seconds**.

Machine metadata: `media-final.json`, `ffprobe-final.json`, and `render.log`.

## Strict composition checks

`hyperframes check --samples 18 --snapshots --timeout 30000 --strict --browser-gpu --json`

**Passed with zero errors, warnings, or informational findings** across lint, runtime, layout, motion, and contrast. The final audit covered 18 layout samples, 300 motion samples, and 14 contrast checks at five sampled frames; all 14 passed. Evidence: `check-final.json`.

The mandatory unpinned latest-CLI probe confirmed **0.8.31** is current and no upgrade is available: `upgrade-context-check.json`. Hyperframes, GSAP, Three.js, and esbuild are pinned in the package and lockfile.

## Actual inside and assembly animation

The eight-second sequence uses the actual A03 GLB, with the same part-name rules and local Y separation as the website's assembly explorer. The complete device opens into five opaque groups, holds an angled view of the board and cell, and returns to its exact assembled positions. No photographic stand-in or transparent duplicate shell is used for that motion.

- GLB SHA-256: `E1D14CDB47A5563D0B55B8DAD511A1A651CCCDDF62F40B9147E9E0E0A2D0D342`.
- Staged model was verified byte-for-byte against `../../../enclosure/aura-device.glb`.
- Assembled pose: **21.7 s**. Interior hold: **24.2 s**. Reassembled pose: **28.4 s**.
- Source model contains 87 nodes classified into five nonempty groups.
- Reverse and repeated seek calculations return identical transforms; assembled endpoints have exactly zero separation. Evidence: `context-validation.json`.
- Final full-frame pose snapshots: `assembly-snapshots-final/`.
- Six frames extracted from the completed MP4: `assembly-encoded.jpg` at 21.7, 22.6, 24.2, 25.6, 27.4, and 28.4 s.

Source and encoded beginning, intermediate, inside-hold, and ending poses were visually inspected. The board and cell remain distinct, surfaces stay opaque, and the same geometry visibly closes. The parent independently reviewed both the initial pose sheet and final encoded contact sheet. The keyframes ghost diagnostic was also run; its static analyzer does not enumerate the analytic canvas callback, so full-frame seek images and encoded frames provide the visual evidence.

The fixed studio environment is prefiltered once and supplied as a local half-float texture, preserving reflections while avoiding environment convolution during rendering. The initial Intel Direct3D compiler warning is retained in `check-before-environment-bake.json` and `environment-bake.json`; it is absent from the final strict check. No warnings were filtered or hidden. A slow software-renderer check was stopped; its status is recorded in `check-software-incomplete.json`.

## Encoded media and accessibility

FFmpeg decoded all **1,320 frames** with exit code zero. Audio measured **−22.2 dBFS mean** and **−7.9 dBFS peak**: present and unclipped. Evidence: `decode-audio.log`.

The nine-frame scene overview (`../renders/contact-sheet.jpg`), six assembly frames (`assembly-encoded.jpg`), six transition samples (`transitions-final.jpg`), and exact final frame 1,319 (`final-frame.png`) were visually inspected. Text and imagery remain clear, dissolves are clean, and the final brand card holds to the last frame. The poster (`../renders/poster.jpg`) is extracted from the final MP4 at **41.8 seconds** and carries the exact primary line.

The English WebVTT has **15 ordered, non-overlapping cues** ending at **44 seconds**, including descriptions of the opening layers, internal board/cell, and reassembly. Evidence: `captions-check.json`. `scripts/export-review.mjs` reproduces decoding, metadata assertions, poster, contact sheets, and final frame.

## Provenance and scope

All five photographs retain their approved A03 hashes. Profile and detail were previously rendered from the corrected Blender scene using `../scripts/render_a03_still.py`, without geometry edits. Hero aliases have identical source pixels. Image provenance: `plate-detail.json`, `plate-profile.json`; final asset hashes: `assets-final.json`. No A01 or A02 imagery appears in this film.

The original ambient score was extended to 44 seconds with an additional harmonic passage. It remains locally synthesized, without stock music, voices, or external samples. `npm run score` reproduces it.

The preceding A03 movie and source remain in Git commit `1569645a292b8bd147bb208ccc96d9fe8081adc5`; this revision creates no additional media archive. All source and assets are local. No hosted rendering, external publishing, or feedback submission was performed by the film task.

Manual capture, physical microphone disconnect, illustrative notes, reference internal components, and the development qualifier remain explicit. Context refers to moments a person chooses to capture. The film does not imply always-on recording, perfect memory, manufacturing validation, production readiness, measured battery life, stock, or a shipping date.
