import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { generateKeyPairSync, createPublicKey } from 'node:crypto';
import { spawnSync } from 'node:child_process';

// Run after `npx convex dev --once`. Never prints keys or replaces existing keys.
const envPath = '.env.local';
const contents = readFileSync(envPath, 'utf8');
const env = Object.fromEntries(contents.split(/\r?\n/).filter(line => /^[A-Z_]+=/.test(line)).map(line => { const i = line.indexOf('='); return [line.slice(0, i), line.slice(i + 1).replace(/^"|"$/g, '')]; }));
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(env.CONVEX_URL ?? '')) throw new Error('This setup helper only configures the local Convex deployment.');
let next = contents;
for (const [key, value] of Object.entries({ NEXT_PUBLIC_CONVEX_URL: env.CONVEX_URL, NEXT_PUBLIC_CONVEX_SITE_URL: env.CONVEX_SITE_URL })) {
  if (!value) throw new Error(`Missing ${key}`);
  next = next.replace(new RegExp(`^${key}=.*\\r?\\n?`, 'gm'), '');
  next += `\n${key}=${value}\n`;
}
writeFileSync(envPath, next);
mkdirSync('.convex', { recursive: true });
const keyPath = '.convex/.env.auth-local';
if (!existsSync(keyPath)) {
  const { privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048, privateKeyEncoding: { type: 'pkcs8', format: 'pem' }, publicKeyEncoding: { type: 'spki', format: 'pem' } });
  const publicKey = createPublicKey(privateKey).export({ format: 'jwk' });
  writeFileSync(keyPath, `JWT_PRIVATE_KEY="${privateKey.trimEnd().replace(/\n/g, ' ')}"\nJWKS=${JSON.stringify({ keys: [{ use: 'sig', ...publicKey }] })}\nSITE_URL=http://127.0.0.1:3000\n`, { mode: 0o600 });
}
const command = process.platform === 'win32' ? 'cmd.exe' : 'npx';
const args = process.platform === 'win32' ? ['/d', '/s', '/c', 'npx convex env set --from-file .convex/.env.auth-local'] : ['convex', 'env', 'set', '--from-file', keyPath];
const result = spawnSync(command, args, { stdio: 'pipe', encoding: 'utf8' });
if (result.status !== 0) throw new Error('Local Convex environment setup failed. Run the documented CLI command; no key contents were printed.');
console.log('Local Convex signing keys and Next.js public URLs configured. Secrets remain in ignored files.');
