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
  vm.runInNewContext(code, { module: compiled, exports: compiled.exports, require: (name: string) => dependencies[name] ?? require(name) });
  return compiled.exports;
}
const channels = compile("./official-channels.ts");
const component = compile("../app/components/FixtureOfficialActions.tsx", { "../../lib/official-channels": channels }) as { default: React.ComponentType<Record<string, unknown>> };
const digital = { official_homepage_url: "https://club.test/", official_instagram_url: "https://www.instagram.com/club/" };
const ticket = { label: "Buy tickets", url: "https://club.test/tickets", source_label: "Club" };
function render(props: Record<string, unknown>) { return renderToStaticMarkup(React.createElement(component.default, { teamName: "Club", ...props })); }
const cases = [
  ["online and both channels", { ticketAction: ticket, channels: digital }, ["Buy tickets", "Club website", "Instagram"]],
  ["information and both channels", { ticketAction: { ...ticket, label: "Ticket info" }, channels: digital }, ["Ticket info", "Club website", "Instagram"]],
  ["digital only", { channels: digital }, ["Club website", "Instagram"]],
  ["ticket only", { ticketAction: ticket }, ["Buy tickets"]],
  ["website only", { channels: { official_homepage_url: digital.official_homepage_url } }, ["Club website"]],
  ["Instagram only", { channels: { official_instagram_url: digital.official_instagram_url } }, ["Instagram"]],
  ["nothing", {}, []],
  ["protected blank guidance plus digital", { ticketAction: null, channels: digital }, ["Club website", "Instagram"]],
  ["approved HTTP unchanged", { ticketAction: { ...ticket, url: "http://biljetter.hbk.se/" } }, ["Buy tickets"]],
  ["resolver suppressed arbitrary HTTP", { ticketAction: null }, []],
] as const;
for (const [name, props, expected] of cases) test(name, () => {
  const html = render(props);
  assert.deepEqual([...html.matchAll(/<span>([^<]+)<\/span>/g)].map(m => m[1]), expected);
  assert.equal((html.match(/<nav /g) ?? []).length, expected.length ? 1 : 0);
  assert.equal((html.match(/<a /g) ?? []).length, expected.length);
  if (expected.length) { assert.match(html, /min-h-12 w-full/); assert.match(html, /rel="noopener noreferrer"/); assert.match(html, /opens in a new tab/); }
  if (name === "approved HTTP unchanged") assert.match(html, /href="http:\/\/biljetter.hbk.se\/"/);
});
test("fixture has one action panel, preserves protected guidance and no standalone CTA", () => {
  const page = readFileSync(new URL("../app/fixture/[fixtureId]/page.tsx", import.meta.url), "utf8");
  assert.equal((page.match(/<FixtureOfficialActions /g) ?? []).length, 1);
  assert.match(page, /channels=\{data\.official_channels\}/);
  assert.match(page, /!data\.ticket_action && data\.ticket_guidance/);
  assert.match(page, /data\.ticket_guidance\.message/);
  assert.doesNotMatch(page, /href=\{data\.ticket_action\.url\}|officialChannelLinks|href=\{data\.ticket_guidance/);
});
