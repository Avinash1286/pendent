// Read-only README illustration of the released native copper layers.
// Requires KiCad 10 CLI and `npm ci` in website/ (Sharp).
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
const sharp = createRequire(new URL('../../website/package.json', import.meta.url))('sharp');

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const board = path.join(root, 'hardware/native/aura-a03.kicad_pcb');
const output = path.join(root, 'docs/assets');
const cli = process.env.KICAD_CLI || (process.platform === 'win32'
  ? 'C:/Program Files/KiCad/10.0/bin/kicad-cli.exe' : 'kicad-cli');
const sha = data => crypto.createHash('sha256').update(data).digest('hex');
const before = sha(await fs.readFile(board));
await fs.mkdir(output, { recursive: true });
const drawings = [];
for (const [side, layer] of [['front', 'F.Cu'], ['back', 'B.Cu']]) {
  const target = path.join(output, `pcb-${side}.svg`);
  execFileSync(cli, ['pcb', 'export', 'svg', '--layers', `${layer},Edge.Cuts`,
    '--mode-single', '--page-size-mode', '2', '--fit-page-to-board',
    '--exclude-drawing-sheet', '--drill-shape-opt', '2',
    ...(side === 'back' ? ['--mirror'] : []), '--output', target, board], { stdio: 'pipe' });
  const raw = await fs.readFile(target, 'utf8');
  const viewBox = raw.match(/viewBox="([^"]+)"/)[1];
  const [, , width, height] = viewBox.split(/\s+/).map(Number);
  const paths = raw.slice(raw.indexOf('<g '), raw.lastIndexOf('</svg>'))
    .replaceAll(/#(?:C83434|4D7FC4)/g, '#d4b786')
    .replaceAll('#D0D2CD', '#899b90').replaceAll('#FFFFFF', '#172b26');
  // The green fill is illustrative; native copper/outline paths are unchanged.
  drawings.push(`<svg x="${side === 'front' ? 280 : 920}" y="190" width="320" height="560" viewBox="${viewBox}">
    <rect x="0" y="0" width="${width}" height="${height}" rx="10" fill="#172b26"/>
    ${paths}</svg>`);
}
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1520" height="940" viewBox="0 0 1520 940">
  <rect width="1520" height="940" fill="#f4f3ef"/>
  <g font-family="Arial, sans-serif" fill="#222c28">
    <text x="76" y="78" font-size="19" letter-spacing="4">AURA / EVT–A03</text>
    <text x="76" y="135" font-size="43" font-weight="600">A small board. Every connection considered.</text>
    <line x1="760" x2="760" y1="198" y2="786" stroke="#d9ddd6"/>
    ${drawings.join('')}
    <text x="440" y="802" text-anchor="middle" font-size="27">Front copper</text>
    <text x="1080" y="802" text-anchor="middle" font-size="27">Back copper · mirrored</text>
    <text x="760" y="864" text-anchor="middle" font-size="21" fill="#68746b">24 × 42 mm · 0.8 mm · 4 copper layers</text>
    <text x="760" y="909" text-anchor="middle" font-size="16" fill="#68746b">Native KiCad layer plots · illustrative colours · prototype assembly review pending</text>
  </g>
</svg>`;
const image = path.join(output, 'pcb-layout.png');
await sharp(Buffer.from(svg)).png({ compressionLevel: 9 }).toFile(image);
if (sha(await fs.readFile(board)) !== before) throw new Error('Board changed during illustration export');
await fs.writeFile(path.join(output, 'pcb-layout-provenance.json'), JSON.stringify({
  input: 'hardware/native/aura-a03.kicad_pcb', boardSha256: before, boardUnchanged: true,
  method: 'Native front/back copper and Edge.Cuts SVG plots; back mirrored; illustrative colours and substrate fill.',
  output: 'docs/assets/pcb-layout.png', sha256: sha(await fs.readFile(image)),
}, null, 2) + '\n');
console.log('Created README PCB illustration; native board unchanged.');
