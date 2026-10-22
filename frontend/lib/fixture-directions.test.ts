import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);
function compile(path: string, dependencies: Record<string, unknown> = {}) {
  const compiled = { exports: {} };
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  vm.runInNewContext(code, { AbortController, module: compiled, exports: compiled.exports, require: (name: string) => dependencies[name] ?? require(name) });
  return compiled.exports;
}
const dependencies = { "../../lib/api": { get: () => Promise.resolve({ data: null }) }, "../../lib/venue-guide": compile("./venue-guide.ts") };
type DirectionsComponent = { default: React.ComponentType<Record<string, unknown>> };
async function directionsFor(venueId: number | null, data: unknown) {
  let stored: unknown = null;
  const requests: string[] = [];
  const hooks = { ...React, useState: (initial: unknown) => [initial, (value: unknown) => { stored = value; }], useEffect: (fn: () => unknown, deps: unknown[]) => { if (deps.length) fn(); } };
  const mocked = compile("../app/components/FixtureDirections.tsx", { ...dependencies, react: hooks, "../../lib/api": { get: async (path: string) => { requests.push(path); return { data }; } } }) as DirectionsComponent;
  renderToStaticMarkup(React.createElement(mocked.default, { teamName: "Club", venueId }));
  await Promise.resolve(); await Promise.resolve();
  return { stored, requests };
}
test("directions resolve only the fixture venue, including canonical equivalences, never the club's usual ground", async () => {
  const result = await directionsFor(99, { venue_id: 51, latitude: 51.5, longitude: -0.1 });
  assert.deepEqual(result.requests, ["/venue/99"]);
  assert.deepEqual(JSON.parse(JSON.stringify(result.stored)), { venueId: 99, url: "https://www.google.com/maps/dir/?api=1&destination=51.5%2C-0.1" });
});
test("invalid or missing canonical coordinates never produce a directions destination", async () => {
  for (const data of [null, {}, { latitude: null, longitude: 0 }, { latitude: 91, longitude: 0 }, { latitude: 0, longitude: 181 }, { latitude: "51", longitude: 0 }]) assert.equal((await directionsFor(99, data)).stored, null);
  assert.deepEqual((await directionsFor(null, { latitude: 51, longitude: 0 })).requests, []);
});
test("compact directions use a green outline and omit stale destinations", () => {
  const ready = compile("../app/components/FixtureDirections.tsx", { ...dependencies, react: { ...React, useState: () => [{ venueId: 99, url: "https://www.google.com/maps/dir/?api=1&destination=51%2C0" }, () => undefined] } }) as DirectionsComponent;
  const html = renderToStaticMarkup(React.createElement(ready.default, { venueId: 99 }));
  assert.match(html, /DIRECTIONS/); assert.match(html, /min-h-11 shrink-0/);
  assert.match(html, /border-\[var\(--mg-green\)\]/); assert.doesNotMatch(html, /bg-\[var\(--mg-green\)\]/);
  assert.match(html, /target="_blank" rel="noopener noreferrer"/);
  assert.equal(renderToStaticMarkup(React.createElement(ready.default, { venueId: 100 })), "");
  const page = readFileSync(new URL("../app/fixture/[fixtureId]/page.tsx", import.meta.url), "utf8");
  assert.match(page, /<FixtureDirections venueId=\{data\.fixture\.venue_id\}/);
  assert.ok(page.indexOf("<FixtureDirections") < page.indexOf("<FixtureOfficialActions"));
});

test("a late venue response after navigation cannot restore stale directions", async () => {
 let settle: (value: unknown) => void = () => undefined;
 let cleanup: (() => void) | undefined;
 let stored: unknown = null;
 const pending = new Promise(resolve => { settle = resolve; });
 const hooks = { ...React, useState: (initial: unknown) => [initial, (value: unknown) => { stored = value; }], useEffect: (fn: () => (() => void) | undefined, deps: unknown[]) => { if (deps.length) cleanup = fn(); } };
 const mocked = compile("../app/components/FixtureDirections.tsx", { ...dependencies, react: hooks, "../../lib/api": { get: () => pending } }) as DirectionsComponent;
 renderToStaticMarkup(React.createElement(mocked.default, { teamName: "Club", venueId: 99 }));
 cleanup?.(); settle({ data: { latitude: 51, longitude: 0 } }); await Promise.resolve(); await Promise.resolve();
 assert.equal(stored, null);
});
