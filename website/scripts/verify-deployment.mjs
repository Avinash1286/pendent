import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const website = 'https://pendent-eight.vercel.app';
const paths = ['/', '/product/aura.glb', '/film/aura-launch.mp4', '/film/captions.vtt', '/film/poster.jpg'];
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
const checks = await Promise.all(paths.map(async (path) => {
  const response = await fetch(`${website}${path}`, { signal: AbortSignal.timeout(60000) });
  assert.equal(response.status, 200, `${path} HTTP status`);
  const bytes = Buffer.from(await response.arrayBuffer());
  const check = {
    url: response.url,
    status: response.status,
    contentType: response.headers.get('content-type'),
    bytes: bytes.length,
  };
  if (path !== '/') {
    const source = await readFile(new URL(`../public${path}`, import.meta.url));
    check.sha256 = sha256(bytes);
    check.matchesSource = check.sha256 === sha256(source);
    assert.ok(check.matchesSource, `${path} differs from the local published asset`);
  }
  return check;
}));
const report = {
  website,
  deploymentId: process.argv[2] ?? null,
  checkedAt: new Date().toISOString(),
  browserInteractionQA: false,
  filmDurationSeconds: 44,
  checks,
};
await writeFile(new URL('../../docs/deployment-verification.json', import.meta.url), `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report, null, 2));
