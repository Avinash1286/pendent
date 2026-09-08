# AURA launch film

An original 44-second product concept film built around **“Capture the context of your life.”** The story connects life's passing thoughts and moments with personal choice and new possibilities. Hyperframes 0.8.31, actual A03 Blender enclosure renders, a real animated inside view, and an original local soundtrack preserve the quiet, cinematic presentation.

## Deliverables

- `renders/aura-launch.mp4` — final 1920×1080, 30 fps H.264/AAC video.
- `captions.vtt` — English captions describing the on-screen message and illustrative note.
- `renders/poster.jpg`, `renders/contact-sheet.jpg` — website poster and scene overview.
- `index.html` — editable Hyperframes composition, one paused seekable GSAP timeline.
- `STORYBOARD.md`, `BRIEF.md`, `frame.md` — narrative, product constraints, and visual direction.
- `assets/aura-score.wav`, `scripts/score.mjs` — original soundtrack and reproducible source.
- `assets/aura-device.glb`, `scripts/assembly-scene.mjs`, `scripts/assembly-model.mjs` — actual enclosure geometry and seekable Three.js assembly shot.
- `qa/` — visual and tool validation evidence.

Final output metadata, strict Hyperframes checks, full decoding, audio, captions, and visual verification are recorded in `qa/VERIFICATION.md`.

Verified final MP4: **44.000 seconds, 1,320 frames, 13,469,070 bytes**. SHA-256: `1F208827348028C6ABA7508524E1D1DA0FFA45779663BF3BF75E97FB6CDFAEE0`. Strict checks have zero findings; all frames decode successfully.

## Reproduce locally

Requires Node.js 22+ and FFmpeg/FFprobe on PATH. From this directory:

```powershell
npm ci
npx hyperframes browser ensure
npm run score
npm run build:assembly
node scripts/verify-context.mjs
npm run check
npm run render
npm run dev
```

The preview command starts managed Hyperframes Studio in the background. The final film uses only staged local assets and a packaged font; rendering requires no HeyGen account, voice service, remote music catalog, or media generation API.

To regenerate the detail and profile photographs, `scripts/render_a03_still.py` loads the saved `../../enclosure/aura-product.blend` scene in Blender 5.2.1 LTS. Run each view in its own Blender process using the commands in that script's header. It changes only camera, render visibility, and output settings; it does not rebuild or save geometry. Source-scene hashes, camera poses, output sizes, and image hashes are recorded in `qa/plate-detail.json` and `qa/plate-profile.json`.

On the installed Windows environment, Blender is at `C:/Program Files/Blender Foundation/Blender 5.2/blender.exe`. For example, from this directory:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background '../../enclosure/aura-product.blend' --python 'scripts/render_a03_still.py' -- detail
```

Replace `detail` with `profile` for the second plate.

## Design truth

The object and its controls come from the actual A03 Blender case built alongside the PCB. The complete black front face is the recording paddle; the physical microphone disconnect is on the silver side frame. The film presents intended interactions and an explicitly illustrative phone-and-cloud notes interface. It makes no claim of production readiness, validated battery life, certification, availability, or a shipping date.

The verified original A01 film and complete source are preserved in `../archive/A01`. The unreleased A02 source draft is preserved in `../archive/A02-draft`. The current source is A03.

The preceding A03 film and source remain in Git commit `1569645a292b8bd147bb208ccc96d9fe8081adc5`. This revision preserves the product photographs and established scene motion, adds an eight-second inside/assembly sequence, and extends the original score. It creates no additional media archive. The latest-CLI probe confirmed Hyperframes 0.8.31 remains current.

## Audio

Original stereo ambient score: 48 kHz/16-bit PCM, 44 s. A locally synthesized suspended harmonic progression, sparse bell tones, and controlled delay, with no sampled music, external voices, or unlicensed audio. Fades are baked into the source to make output deterministic; final encoded levels are recorded in `qa/VERIFICATION.md`.

## Inside and assembly sequence

The actual A03 GLB opens into five opaque groups, holds an angled view of its board and cell, then reassembles. Group classification and local-axis separation match the website's assembly explorer. The camera and part transforms are pure functions of film time, making reverse and random seeks repeatable. The sequence illustrates design structure; internal shapes include reference component envelopes and do not prove production fit.

The latest model incorporates the frozen nine-component PCB placement corrections and dimension-driven internal package proxies. Its 89 nodes preserve the same five animation groups. The case's eight print files are byte-for-byte unchanged; the enclosure package independently verifies 56 exported package transforms and 50 body dimensions. This film refresh changes only the internal model and its rendered sequence. The story, exterior photographs, score, timing and captions remain unchanged. See [mechanical package details](../../enclosure/PACKAGE-ENVELOPES.md) and [final film verification](qa/VERIFICATION.md).

The subsequent C18 orientation-only source correction records 270° while retaining its symmetric visual body at 90°. The model audit explicitly reports **55 exact rotations plus one proven C18 body-symmetry match**, with no unintended deviations. Complete triangle and shading-normal invariance is verified in all three GLBs. The saved models and this already-verified film remain byte-for-byte unchanged; PCB pin orientation remains explicit in the hardware source.

The prior assembly film/source checkpoint is Git commit `4d62c6b2f379fb410dc97941b622431bd6104f9b`. Current model/media handoff hashes are in [mechanical-sync-release.json](qa/mechanical-sync-release.json). No additional video archive was created for this sync.

Three.js and its addons are bundled locally with esbuild. A fixed studio environment is prefiltered once and stored locally as a half-float texture. This preserves the reflections and avoids procedural environment convolution during video rendering. `npm run bake:environment` regenerates it using the bundled Chrome runtime (or a `CHROME_PATH` override); ordinary rendering uses the supplied texture. Strict checking remains enabled. No diagnostic overlays appear in the movie.

## Sources

- Hyperframes: https://github.com/heygen-com/hyperframes
- Hyperframes quickstart: https://hyperframes.heygen.com/quickstart
- Manrope: https://github.com/google/fonts/tree/main/ofl/manrope

See `LICENSES.md` for asset provenance. No public publishing command was executed.
