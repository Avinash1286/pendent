# AURA product experience

React 19, TypeScript, Vite 8, Three.js and the Base UI dialog primitive. This is a static product presentation, with no secrets or server runtime in the browser bundle.

## Run locally

```sh
npm ci
npm run dev
```

## Validate and build

```sh
npm run lint
npx tsc --noEmit
node scripts/verify-model.mjs
npm run build
```

The lint configuration checks authored application code. Unmodified generated UI catalog files have upstream lint incompatibilities and are excluded from that lint pass; TypeScript still checks the full project. The site uses only the catalog's dialog and button primitives.

## Features

- Blender-generated GLB with studio lighting, drag rotation and keyboard rotation.
- Three finish choices, persisted locally where storage is available.
- Animated exploded/assembled view and camera reset.
- Guided sample recording, transfer and AI-note flow. No live microphone or AI requests.
- Modal 36-second launch film with English title captions and download.
- Downloadable JSON product configuration. No reservation, order or payment is created.
- Responsive styling, reduced-motion support, keyboard focus and image fallback if WebGL fails.

## Direct Vercel deployment

The Vercel project uses this repository with **Root Directory `website`**. CLI deployment runs from the repository root after project linking there:

```sh
cd ..
vercel link --project pendent
vercel deploy --prod
```

The root `.vercelignore` excludes hardware/render workspaces while retaining website assets. `website/vercel.json` sets the static Vite build and security headers. Automatic Git deployments are disabled so development checkpoints can be pushed independently; validated releases use the Vercel CLI directly. There are no GitHub Actions workflows.

## Asset provenance

Product models/renders originate in `../enclosure`. Video and captions originate in `../film/aura-launch`. The Manrope variable font is redistributed under its SIL Open Font License in `public/fonts/OFL.txt`. The release README provides the final site URL.

## Commerce boundary

179 USD is a proposed target price. The concept is not offered for sale; the configuration download is intentionally clear about that status. A live storefront requires validated hardware, actual inventory/fulfillment terms and an authorized merchant integration.
