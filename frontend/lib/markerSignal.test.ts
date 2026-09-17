import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { markerSignalForFixture } from "./markerSignal.ts";

const markerSource = readFileSync(new URL("../app/components/groundMarkerIcon.ts", import.meta.url), "utf8");
const mapSource = readFileSync(new URL("../app/components/FixtureMap.tsx", import.meta.url), "utf8");

test("marker signal follows the complete fixed precedence", () => {
  const allEditorialSignals = ["SIGNIFICANT_RIVALRY", "FOOTBALL_LANDMARK", "UNIQUE_SETTING", "CLASSIC_GROUND"];
  assert.equal(markerSignalForFixture({ fixture_type: "international", decision_attribute_keys: allEditorialSignals }), "international");
  assert.equal(markerSignalForFixture({ fixture_type: "cup", decision_attribute_keys: allEditorialSignals }), "cup");
  assert.equal(markerSignalForFixture({ fixture_type: "standard", decision_attribute_keys: allEditorialSignals }), "rivalry");
  assert.equal(markerSignalForFixture({ fixture_type: "standard", decision_attribute_keys: ["FOOTBALL_LANDMARK", "CLASSIC_GROUND"] }), "scenic");
  assert.equal(markerSignalForFixture({ fixture_type: "standard", decision_attribute_keys: ["UNIQUE_SETTING", "CLASSIC_GROUND"] }), "scenic");
  assert.equal(markerSignalForFixture({ fixture_type: "standard", decision_attribute_keys: ["CLASSIC_GROUND"] }), "classic");
  assert.equal(markerSignalForFixture({ fixture_type: "standard", decision_attribute_keys: [] }), "standard");
});

test("missing or unrelated DECIDE attributes safely use the standard signal", () => {
  assert.equal(markerSignalForFixture({}), "standard");
  assert.equal(markerSignalForFixture({ fixture_type: "unknown", decision_attribute_keys: ["EXCEPTIONAL_SUPPORT"] }), "standard");
});

test("all six signals use one central SVG while dimensions and tap target stay unchanged", () => {
  for (const signal of ["international", "cup", "rivalry", "scenic", "classic"] as const) {
    assert.match(markerSource, new RegExp(`signal === "${signal}"`));
  }
  assert.doesNotMatch(markerSource, /M6 21V10H9L15 17L21 10H24V21/);
  assert.doesNotMatch(markerSource, /semanticBadge/);
  assert.doesNotMatch(markerSource, /visited \? `/);
  assert.match(markerSource, /iconSize: \[VENUE_MARKER_DESIGN\.hitSize, VENUE_MARKER_DESIGN\.hitSize\]/);
  assert.match(markerSource, /iconAnchor: \[VENUE_MARKER_DESIGN\.hitSize \/ 2, VENUE_MARKER_DESIGN\.hitSize - 2\]/);
  assert.match(mapSource, /icons\[markerSignal\]/);
});
