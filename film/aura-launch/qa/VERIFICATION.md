# A03 final film verification

Completed 8 September 2026 (Asia/Katmandu).

## Final artifact

- File: `../renders/aura-launch.mp4`
- Renderer: Hyperframes 0.8.31, high quality, one worker.
- Duration: **36.000000 seconds**.
- Picture: **1920×1080, 30 fps, 1,080 H.264 frames**; YUV420p, BT.709.
- Audio: **AAC, 48 kHz, stereo**.
- Size: **9,568,971 bytes** (9.1 MiB).
- SHA-256: `5ACDFFF5B26622E3BD28C9F58957FF276FCA7F10C337D3C5F22CF79F88016295`.
- Successful render time: **2 minutes 5.3 seconds**.

## Composition checks

`hyperframes check --samples 15 --snapshots --timeout 30000 --strict --json`

Passed with **zero errors, warnings, or informational findings** across lint, runtime, layout, motion, and contrast. This final audit used the corrected A03 plates and covered 15 layout samples, 300 motion samples, and 24 contrast checks at five sampled frames; all 24 passed. Machine output: `check-final.json`.

The focused keyframe diagnostic records the hero's continuous photographic reframe in `keyframes-a03-hero.log`. Full-frame snapshots verify the visible result; the diagnostic's colored bounds are inspection overlays and are not part of the film.

## Encoded media checks

FFmpeg decoded the complete MP4 through all **1,080 frames**, with exit code zero. Audio measured **−22.4 dBFS mean** and **−7.9 dBFS peak**: present and unclipped. Logs: `decode-audio.log`, `ffprobe-final.json`, and `render.log`.

The encoded six-scene overview (`../renders/contact-sheet.jpg`), ten transition samples (`transitions-final.jpg`), and the final frame at 35.966 seconds (`final-frame.png`) were visually inspected. Images and text are present, scene handoffs remain clean, and the chain stays clear of the closing tagline. The completed brand card holds to the last frame. The poster (`../renders/poster.jpg`) comes from the final MP4 at 8.8 seconds.

The English WebVTT file has **12 ordered, non-overlapping cues** ending at exactly **36 seconds**. Evidence: `captions-check.json`.

## Product image provenance

The film depicts the A03 capsule selected from the user's reference: glossy black full-face recording paddle, satin silver frame, fine chain, and physical side microphone disconnect. There is no A01 or A02 product imagery in the final film.

The hero plate is the approved enclosure render. Its macro and closing aliases have identical SHA-256 hashes, verified in `assets-a03.json`. The detail and profile plates were rendered from the saved, corrected Blender scene using `../scripts/render_a03_still.py`, without rebuilding or saving geometry. Camera positions exactly match the enclosure renderer.

- Blender: **5.2.1 LTS**, Cycles CPU, 32 samples, denoising.
- Source-scene SHA-256: `cd75667b45134149fb798954fe6d87084443b61e6502ae5b53b99a274f15dec8`.
- Detail: **2000×1600 RGBA**, rendered and visually inspected; false shading dents around the privacy slider are absent.
- Profile: **2200×1800 RGBA**, rendered and visually inspected; chain visibility matches the enclosure profile camera setup.
- Per-view metadata and hashes: `plate-detail.json`, `plate-profile.json`.
- Renderer logs: `blender-detail.log`, `blender-profile.log`.

Each still used a separate Blender process and exited successfully. The original enclosure batch had stopped after the hero; the render-only recovery preserved the approved geometry.

## Reproducibility and scope

Hyperframes and GSAP are pinned with a lockfile. All product images, the Manrope font, GSAP, and the original score are local. The 36-second score is reproducible with `npm run score`; no stock music, voices, or external samples are used. The source motion is one paused, deterministic GSAP timeline. The original A01 edition remains preserved in `../../archive/A01`, and the unrendered A02 draft in `../../archive/A02-draft`.

One initial five-second FFmpeg startup probe timed out. The installed FFmpeg binary was verified directly and the same render completed successfully on retry; the earlier probe log is retained as `render-ffmpeg-probe-retry.log`.

No hosted video rendering, credentialed media generation, external publishing, or feedback submission was used. The user's standing instruction to make all decisions authorized local final rendering. The notes surface remains explicitly illustrative, and the final card identifies the development stage and engineering validation. The film does not claim production readiness, measured battery life, certification, availability, or a shipping date.
