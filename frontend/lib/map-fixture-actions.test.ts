import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
const require = createRequire(import.meta.url);
const source = readFileSync(new URL("../app/components/MapFixtureActions.tsx", import.meta.url), "utf8");
const mod = { exports: {} as { default: React.ComponentType<Record<string, unknown>> } };
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText, { module: mod, exports: mod.exports, require: (name: string) => name === "next/link" ? { __esModule: true, default: (p: Record<string, unknown>) => React.createElement("a", p) } : name.endsWith(".css") ? { __esModule: true, default: {} } : require(name) });
for (const saved of [false, true]) test(`map actions reflect saved=${saved} without changing attendance or Going`, () => {
  const html = renderToStaticMarkup(React.createElement(mod.exports.default, { fixtureId: 123, interestedFixtureIds: saved ? [123] : [], updatingFixtureIds: [], onToggleInterested: () => undefined }));
  assert.match(html, /href="\/fixture\/123"/); assert.match(html, /VIEW MATCH/);
  assert.match(html, saved ? /REMOVE FROM MY MATCHDAYS/ : /ADD TO MY MATCHDAYS/);
  assert.match(html, new RegExp(`aria-pressed="${saved}"`)); assert.doesNotMatch(html, /Going|Went|attendance/);
});
test("in-flight save disables repeat actions accessibly", () => {
 const html = renderToStaticMarkup(React.createElement(mod.exports.default, { fixtureId: 123, interestedFixtureIds: [], updatingFixtureIds: [123], onToggleInterested: () => undefined }));
 assert.match(html, /disabled=""/); assert.match(html, /aria-busy="true"/);
});
