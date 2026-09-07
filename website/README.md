# AURA product experience

React 19, TypeScript, Vite 8, Three.js and Base UI primitives. This is a static product presentation, with no secrets or server runtime in the browser bundle.

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
node scripts/verify-framing.mjs
node scripts/verify-assets.mjs
npm run build
```

The lint configuration checks authored application code. Unmodified generated UI catalog files have upstream lint incompatibilities and are excluded from that lint pass; TypeScript still checks the full project. The application uses the dialog and slider primitives.

## Features

The site has three chapters: the product hero with finish selection, the interactive assembly explorer, and a compact notes demo. The film opens from the hero. Component details appear when selected in the explorer; configuration downloads sit beside the finish controls.

- Blender-generated GLB with studio lighting, drag rotation and keyboard rotation.
- Three finish choices shared by the hero and assembly models, persisted locally where storage is available.
- Continuous assembly slider, play/pause, see-through shell, front/profile/three-quarter camera presets and reset.
- Direct model part selection and five layer explanations, with keyboard-accessible alternative controls.
- Guided sample recording, transfer and AI-note flow. No live microphone or AI requests.
- Modal 44-second launch film with the actual model opening into layers and reassembling, English title captions and download.
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

After completing the Blender renders, `node scripts/sync-product-assets.mjs` refreshes the website GLB and optimized WebP images using Sharp. Copy the verified MP4, poster and captions from the film's `renders/` directory and composition root into `public/film/`. The framing check projects actual model vertices across 60 combinations of viewport, assembly progress and camera angle; it is a geometry check, not a browser screenshot test.

## Commerce boundary

The concept is not offered for sale; the configuration download records a finish preference. A live storefront requires validated hardware, actual inventory/fulfillment terms and an authorized merchant integration.
