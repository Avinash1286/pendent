# AURA launch film

An original 36-second product concept film made and rendered with Hyperframes 0.8.31, using actual Blender enclosure renders and a locally composed ambient soundtrack.

## Deliverables

- `renders/aura-launch.mp4` — final 1920×1080, 30 fps H.264/AAC video.
- `captions.vtt` — English captions describing the on-screen message and illustrative note.
- `renders/poster.jpg`, `renders/contact-sheet.jpg` — website poster and six scene overview.
- `index.html` — editable Hyperframes composition, one paused seekable GSAP timeline.
- `STORYBOARD.md`, `BRIEF.md`, `frame.md` — narrative, product constraints, and visual direction.
- `assets/aura-score.wav`, `scripts/score.mjs` — original soundtrack and reproducible source.
- `qa/` — visual and tool validation evidence.

The final file is 8.8 MiB, exactly 36.000 seconds, and contains 1,080 video frames. The strict Hyperframes check passes with zero findings. FFmpeg decoded the entire MP4 successfully; all six scene frames and the final hold were visually inspected. See `qa/VERIFICATION.md` for evidence.

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

## Design truth

The object and its controls come from the actual Blender case built alongside the PCB concept. The film presents intended interactions and a labeled illustrative phone interface. It does not claim an implemented firmware stack, implemented AI companion application, validated battery life, production certification, availability, or a shipping date.

## Audio

Original stereo ambient score: 48 kHz/16-bit PCM, 36 s. A locally synthesized suspended harmonic progression, sparse bell tones, and controlled delay, with no sampled music, external voices, or unlicensed audio. Measured source peak −7.9 dBFS and RMS −22.4 dBFS; fades are baked into the source to make output deterministic.

## Sources

- Hyperframes: https://github.com/heygen-com/hyperframes
- Hyperframes quickstart: https://hyperframes.heygen.com/quickstart
- Manrope: https://github.com/google/fonts/tree/main/ofl/manrope

See `LICENSES.md` for asset provenance. No public publishing command was executed.
