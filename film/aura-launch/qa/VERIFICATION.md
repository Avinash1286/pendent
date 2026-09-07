# Final film verification

Completed 8 September 2026 (Asia/Katmandu).

## Render artifact

- File: `../renders/aura-launch.mp4`
- Renderer: Hyperframes 0.8.31, high quality, one worker.
- Duration: **36.000000 seconds**.
- Picture: **1920×1080, 30 fps, 1,080 H.264 frames**.
- Audio: **AAC, 48 kHz, stereo**.
- Size: **9,251,044 bytes** (8.8 MiB).
- SHA-256: `DDFE7B388EE6171EB22502B7283E24295CD27EFA3E83F8DEDD38038EB5D8602A`.
- Render completed successfully in 1 minute 51.5 seconds.

## Checks

`hyperframes check --samples 15 --snapshots --timeout 30000 --strict --json`

Passed with **zero errors, warnings, or informational findings** across lint, runtime, layout, motion, and contrast. The audit covered 15 layout samples, 300 motion samples, and 31 contrast checks at five sampled frames; all 31 passed. Exact machine output: `check-final.json`.

The completed MP4 was decoded through all 1,080 frames by FFmpeg with exit code zero. The decoded audio measured −22.4 dBFS mean and −7.9 dBFS peak: present, audible, and unclipped. Logs: `decode-audio.log`, `ffprobe-final.json`, `render.log`.

The six scene frames in `../renders/contact-sheet.jpg` and the final rendered frame at 35.966 seconds (`final-frame.png`) were visually inspected. Product assets and text are present and legible; the ending holds on the finished brand card. The motion sidecar verifies title ordering and the intended in-frame elements. The source camera pose and path are recorded in `keyframes-hero.log`.

## Review and reproducibility

Hyperframes Studio started in the background and returned HTTP 200 at:

http://localhost:3076/#project/aura-launch

The package pins Hyperframes 0.8.31 and GSAP 3.14.2, with a lockfile. Fonts, images, and music are staged locally. Manrope's license is included. The source score is independently reproducible using `npm run score`.

No hosted rendering, voice cloning, credentialed media generation, external publishing, or feedback submission was used. The user's instruction to make all decisions and complete the video authorized the final local render without another approval prompt.

## Product scope

The physical views use the final Blender hero and privacy detail renders. The notes interface and recording interaction are explicitly labeled concepts. The film does not claim implemented AI firmware, a deployed companion app, measured battery life, certification, production readiness, a shipping date, or current stock.
