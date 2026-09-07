# AURA A01 — preserved launch-film edition

Archived before the A02 enclosure revision on 2026-09-08. This folder contains the complete original 36-second Hyperframes composition, the actual A01 Blender images, original music and generator, fonts and licenses, pinned package lock, final MP4, captions, and validation evidence.

The only omitted project folders are `node_modules` (restore with `npm ci`) and `.thumbnails` (regenerated cache). Run `npm ci`, then `npm run render` in this directory to reproduce the composition. The render requires FFmpeg and the Hyperframes-managed Chrome Headless Shell; `npx hyperframes browser ensure` installs the pinned browser if needed.

The archived final MP4 is `renders/aura-launch.mp4`, 36.000 seconds, 1920 × 1080, 30 fps, H.264/AAC, 9,251,044 bytes. Its SHA-256 is:

`DDFE7B388EE6171EB22502B7283E24295CD27EFA3E83F8DEDD38038EB5D8602A`

The archive copy was verified against the source hash. This edition shows the original 12 mm A01 body. The active project at `../../aura-launch` is being updated to the slimmer A02 design.
