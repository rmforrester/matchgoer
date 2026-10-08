import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as knowHelpers from "./know-v1.ts";
import type { FixtureKnow, KnowFact } from "./know-v1.ts";

const require = createRequire(import.meta.url);
const compiled = { exports: {} };
const source = readFileSync(new URL("../app/components/FixtureKnow.tsx", import.meta.url), "utf8");
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
vm.runInNewContext(code, { module: compiled, exports: compiled.exports, require: (name: string) => name === "../../lib/know-v1" ? knowHelpers : require(name) });
const component = compiled.exports as { default: React.ComponentType<{ know: FixtureKnow; teamName: string }> };
const empty: FixtureKnow = { fixture_id: 1, team_id: 68, venue_id: 10, club_venue_id: 10, club: [], supporters: [], matchday: [], dont_miss: [], good_to_know: [], before_match: [] };
const fact = (id: number, headline: string | null): KnowFact => ({ know_fact_id: id, headline, content: `Unchanged paragraph ${id}.`, provenance: [] });
const render = (know: FixtureKnow) => renderToStaticMarkup(React.createElement(component.default, { know, teamName: "Bolton" }));

test("single club article leads with its original headline and has only an accessible category", () => {
  const html = render({ ...empty, club: [fact(1, "Why Wanderers?")] });
  assert.match(html, /03 \/ Matchday guide/);
  assert.match(html, /class="sr-only">The club<\/h3>/);
  assert.equal((html.match(/>The club</g) ?? []).length, 1);
  assert.match(html, />Why Wanderers\?</);
  assert.match(html, />Unchanged paragraph 1\.</);
});

test("mixed and multiple articles retain quiet category context and exact text order", () => {
  const value = { ...empty, club: [fact(1, "One"), fact(2, "Two")], supporters: [fact(3, "Three")], matchday: [fact(4, "Four")], dont_miss: [fact(5, "Five")], good_to_know: [fact(6, "Six")] };
  const before = JSON.stringify(value);
  const html = render(value);
  assert.doesNotMatch(html, /class="sr-only">The (club|supporters)/);
  assert.match(html, />The club</);
  assert.match(html, />The supporters</);
  const positions = [4, 5, 6, 1, 2, 3].map(id => html.indexOf(`Unchanged paragraph ${id}.`));
  assert.ok(positions.every((position, i) => position >= 0 && (i === 0 || position > positions[i - 1])));
  assert.equal(JSON.stringify(value), before);
});

test("a headline-free identity keeps its meaningful category visible", () => {
  assert.doesNotMatch(render({ ...empty, club: [fact(1, null)] }), /class="sr-only">The club/);
});

test("optional places preserve names, repeated descriptions and exact Directions URLs", () => {
  const value = { ...empty, before_match: [1, 2].map(id => ({ pre_match_spot_id: id, display_name: `Official Fan Zone ${id}`, classification: "CLUB_MATCHDAY_VENUE" as const, audience: "HOME" as const, supporting_line: `Official Fan Zone ${id} unchanged description.`, location_context: null, directions_url: `https://maps.test/?place=${id}&exact=yes` })) };
  const html = render(value);
  assert.match(html, /04 \/ Before the match/);
  assert.doesNotMatch(html, /03 \/ Matchday guide/);
  for (const spot of value.before_match) {
    assert.ok(html.includes(spot.supporting_line!));
    assert.ok(html.includes(spot.directions_url!.replaceAll("&", "&amp;")));
  }
  assert.ok(html.indexOf("Official Fan Zone 1") < html.indexOf("Official Fan Zone 2"));
  assert.equal(render(empty), "");
});
