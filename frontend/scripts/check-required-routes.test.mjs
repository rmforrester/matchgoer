import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { assertSupportRoute } from './check-required-routes.mjs';

const approvedContent = '<h1>Matchgoer support</h1><a href="mailto:hello@matchgoer.com">Support</a><a href="mailto:privacy@matchgoer.com">Privacy contact</a><a href="/privacy">Privacy policy</a>';

function fixture(t, manifest, html) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'matchgoer-required-route-'));
  t.after(() => {
    assert.equal(path.dirname(path.resolve(root)), path.resolve(os.tmpdir()));
    assert.ok(path.basename(root).startsWith('matchgoer-required-route-'));
    fs.rmSync(root, { recursive: true, force: true });
  });
  fs.mkdirSync(path.join(root, 'server', 'app'), { recursive: true });
  fs.writeFileSync(path.join(root, 'server', 'app-paths-manifest.json'), JSON.stringify(manifest));
  if (html !== undefined) fs.writeFileSync(path.join(root, 'server', 'app', 'support.html'), html);
  return root;
}

test('accepts the compiled support route and required contacts', t => {
  assert.doesNotThrow(() => assertSupportRoute(fixture(t, { '/support/page': 'app/support/page.js' }, approvedContent)));
});

test('rejects a production build without the support route', t => {
  assert.throws(() => assertSupportRoute(fixture(t, { '/privacy/page': 'app/privacy/page.js' }, approvedContent)), /route.*missing/);
});

test('rejects a route entry without its rendered page', t => {
  assert.throws(() => assertSupportRoute(fixture(t, { '/support/page': 'app/support/page.js' })), /ENOENT/);
});

test('rejects missing support contact content', t => {
  assert.throws(() => assertSupportRoute(fixture(t, { '/support/page': 'app/support/page.js' }, '<h1>Matchgoer support</h1>')), /content missing/);
});
