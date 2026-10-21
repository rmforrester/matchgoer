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
const visibility = compile("./fixture-ticket-visibility.ts");
const dependencies = { "../../lib/official-channels": channels, "../../lib/analytics": { trackEvent: () => undefined }, "../../lib/fixture-ticket-visibility": visibility };
const component = compile("../app/components/FixtureOfficialActions.tsx", { ...dependencies, react: { ...React, useState: () => [new Date("2026-10-20T12:00:00Z"), () => undefined] } }) as { default: React.ComponentType<Record<string, unknown>> };

const digital = { official_homepage_url: "https://club.test/", official_instagram_url: "https://www.instagram.com/club/" };
const ticket = { label: "Buy tickets", url: "https://club.test/tickets", source_label: "Club" };
function render(props: Record<string, unknown>) { return renderToStaticMarkup(React.createElement(component.default, { teamName: "Club", fixtureDate: "2026-10-20T19:00:00Z", venueTimezone: "Europe/London", ...props })); }
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
test("fixture has one action panel with protected guidance preceding digital links", () => {
  const page = readFileSync(new URL("../app/fixture/[fixtureId]/page.tsx", import.meta.url), "utf8");
  assert.equal((page.match(/<FixtureOfficialActions /g) ?? []).length, 1);
  assert.match(page, /channels=\{data\.official_channels\}/);
  assert.match(page, /ticketGuidance=\{data\.ticket_guidance\}/);
  assert.doesNotMatch(page, /href=\{data\.ticket_action\.url\}|officialChannelLinks|href=\{data\.ticket_guidance/);
});

test("protected admission text stays exact, ahead of digital links, without a fake ticket URL", () => {
  const html = render({ ticketGuidance: { label: "Admission", message: "Cash only at the gate.", source_label: "Club" }, channels: digital });
  assert.ok(html.indexOf("Cash only at the gate.") < html.indexOf("Club website"));
  assert.equal((html.match(/<a /g) ?? []).length, 2);
  assert.doesNotMatch(html, /Buy tickets|Ticket info/);
  assert.equal(render({ ticketGuidance: { label: "Admission", message: "Cash only at the gate.", source_label: "Club" } }).includes("<a "), false);
});

test("expired or unknown-timezone BUY TICKETS hidden without losing club links or Ticket info", () => {
  for (const props of [{ fixtureDate: "2026-10-19T19:00:00Z" }, { venueTimezone: null }, { venueTimezone: "invalid" }]) {
    const html = render({ ticketAction: ticket, channels: digital, ...props });
    assert.doesNotMatch(html, /Buy tickets|https:\/\/club.test\/tickets/);
    assert.match(html, /Club website/); assert.match(html, /Instagram/);
  }
  assert.match(render({ fixtureDate: "2026-10-19T19:00:00Z", ticketAction: { ...ticket, label: "Ticket info" } }), /Ticket info/);
});

test("server rendering does not flash BUY TICKETS before the client checks time", () => {
  const actual = compile("../app/components/FixtureOfficialActions.tsx", dependencies) as typeof component;
  const html = renderToStaticMarkup(React.createElement(actual.default, { teamName: "Club", ticketAction: ticket, channels: digital, fixtureDate: "2026-10-20T19:00:00Z", venueTimezone: "Europe/London" }));
  assert.doesNotMatch(html, /Buy tickets/); assert.match(html, /Club website/);
});
