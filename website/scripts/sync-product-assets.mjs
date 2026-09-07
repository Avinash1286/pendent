import { copyFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const out = path.join(root, 'website/public/product');
await mkdir(out, { recursive: true });
await copyFile(path.join(root, 'enclosure/aura-device.glb'), path.join(out, 'aura.glb'));
for (const [source, target, width] of [['hero-transparent.png', 'transparent.webp', 1600], ['detail.png', 'detail.webp', 1600], ['hero.png', 'hero.webp', 2000], ['exploded.png', 'exploded.webp', 1800]]) {
  await sharp(path.join(root, 'enclosure/renders', source)).resize({ width, withoutEnlargement: true }).webp({ quality: 88, effort: 6 }).toFile(path.join(out, target));
  console.log(`Updated ${target}`);
}
