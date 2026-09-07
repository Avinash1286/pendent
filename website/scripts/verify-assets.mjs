import fs from 'node:fs';
import assert from 'node:assert/strict';
const base = new URL('../', import.meta.url);
const sourceFiles = ['components/aura-experience.tsx', 'components/device-viewer.tsx', 'app/globals.css', 'index.html'];
const references = new Set();
for (const file of sourceFiles) {
  const source = fs.readFileSync(new URL(file, base), 'utf8');
  for (const match of source.matchAll(/["'(](\/(?:product|film|fonts)\/[^"')]+|\/favicon\.svg)["')]/g)) references.add(match[1]);
}
for (const reference of references) {
  const location = new URL(`public${reference}`, base);
  assert.ok(fs.existsSync(location), `Missing asset: ${reference}`);
  assert.ok(fs.statSync(location).size > 100, `Empty asset: ${reference}`);
}
console.log(JSON.stringify({ status: 'passed', localAssetCount: references.size, assets: [...references].map(reference => ({ path: reference, bytes: fs.statSync(new URL(`public${reference}`, base)).size })) }, null, 2));
