import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export function assertSupportRoute(buildDirectory = path.resolve('.next')) {
  const manifest = JSON.parse(fs.readFileSync(path.join(buildDirectory, 'server', 'app-paths-manifest.json'), 'utf8'));
  assert.ok(Object.hasOwn(manifest, '/support/page'), 'Required public route /support is missing from the build');
  const html = fs.readFileSync(path.join(buildDirectory, 'server', 'app', 'support.html'), 'utf8');
  for (const text of ['Matchgoer support', 'mailto:hello@matchgoer.com', 'mailto:privacy@matchgoer.com', 'href="/privacy"']) {
    assert.ok(html.includes(text), `Required /support content missing: ${text}`);
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  assertSupportRoute();
  console.log('Required public route /support: PASS');
}

