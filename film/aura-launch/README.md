# AURA launch film

An original 36-second product concept film made with Hyperframes 0.8.31, actual A03 Blender enclosure renders, and a locally composed ambient soundtrack. The edit leads with the glossy black capsule's profile, gives its physical controls room to breathe, and closes on a long beauty hold.

## Deliverables

- `renders/aura-launch.mp4` — final 1920×1080, 30 fps H.264/AAC video.
- `captions.vtt` — English captions describing the on-screen message and illustrative note.
- `renders/poster.jpg`, `renders/contact-sheet.jpg` — website poster and six scene overview.
- `index.html` — editable Hyperframes composition, one paused seekable GSAP timeline.
- `STORYBOARD.md`, `BRIEF.md`, `frame.md` — narrative, product constraints, and visual direction.
- `assets/aura-score.wav`, `scripts/score.mjs` — original soundtrack and reproducible source.
- `qa/` — visual and tool validation evidence.

The final A03 MP4 is 9.1 MiB, exactly 36.000 seconds, and contains 1,080 video frames. Strict Hyperframes validation passes with zero findings. Full video decoding, audio levels, captions, scene transitions, and the final hold were verified. See `qa/VERIFICATION.md` for the evidence and artifact hash.

## Reproduce locally

Requires Node.js 22+ and FFmpeg/FFprobe on PATH. From this directory:

```powershell
npm ci
npx hyperframes browser ensure
npm run score
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

## Audio

Original stereo ambient score: 48 kHz/16-bit PCM, 36 s. A locally synthesized suspended harmonic progression, sparse bell tones, and controlled delay, with no sampled music, external voices, or unlicensed audio. Measured source peak −7.9 dBFS and RMS −22.4 dBFS; fades are baked into the source to make output deterministic.

## Sources

- Hyperframes: https://github.com/heygen-com/hyperframes
- Hyperframes quickstart: https://hyperframes.heygen.com/quickstart
- Manrope: https://github.com/google/fonts/tree/main/ofl/manrope

See `LICENSES.md` for asset provenance. No public publishing command was executed.
