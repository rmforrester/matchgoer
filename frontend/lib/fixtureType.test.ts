import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { fixtureTypeLabel, safeFixtureType } from "./fixtureType.ts";

const markerSource = readFileSync(new URL("../app/components/groundMarkerIcon.ts", import.meta.url), "utf8");
const mapSource = readFileSync(new URL("../app/components/FixtureMap.tsx", import.meta.url), "utf8");

test("missing and unknown classifications safely retain the standard marker", () => {
  assert.equal(safeFixtureType(undefined), "standard");
  assert.equal(safeFixtureType(null), "standard");
  assert.equal(safeFixtureType("unexpected"), "standard");
  assert.equal(fixtureTypeLabel("standard"), "Standard fixture");
});

test("cup and international classifications are preserved", () => {
  assert.equal(safeFixtureType("cup"), "cup");
  assert.equal(safeFixtureType("international"), "international");
  assert.equal(fixtureTypeLabel("cup"), "Cup fixture");
  assert.equal(fixtureTypeLabel("international"), "International fixture");
});

test("standard marker rendering has no semantic badge", () => {
  assert.match(markerSource, /if \(fixtureType === "standard"\) return ""/);
  assert.match(markerSource, /iconSize: \[VENUE_MARKER_DESIGN\.hitSize, VENUE_MARKER_DESIGN\.hitSize\]/);
  assert.match(markerSource, /iconAnchor: \[VENUE_MARKER_DESIGN\.hitSize \/ 2, VENUE_MARKER_DESIGN\.hitSize - 2\]/);
});

test("cup and international markers and selected cards use one semantic icon", () => {
  assert.match(markerSource, /fixtureType === "cup"/);
  assert.match(markerSource, /<circle cx="6" cy="6" r="3\.6"/);
  assert.match(mapSource, /icons\[fixtureType\]/);
  assert.equal((mapSource.match(/<FixtureTypeIcon type=\{fixtureType\}/g) ?? []).length, 2);
});
