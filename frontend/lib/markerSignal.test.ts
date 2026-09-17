import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { editorialReasonForMarkerSignal, markerSignalForFixture } from "./markerSignal.ts";

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

test("special signals use one central SVG while standard is a plain marker", () => {
  for (const signal of ["international", "cup", "rivalry", "scenic", "classic"] as const) {
    assert.match(markerSource, new RegExp(`signal === "${signal}"`));
  }
  assert.doesNotMatch(markerSource, /M6 21V10H9L15 17L21 10H24V21/);
  assert.doesNotMatch(markerSource, /semanticBadge/);
  assert.doesNotMatch(markerSource, /visited \? `/);
  assert.match(markerSource, /return "";/);
  assert.match(markerSource, /signal === "rivalry" \|\| signal === "scenic" \|\| signal === "classic"/);
  assert.match(markerSource, /iconSize: \[VENUE_MARKER_DESIGN\.hitSize, VENUE_MARKER_DESIGN\.hitSize\]/);
  assert.match(markerSource, /iconAnchor: \[VENUE_MARKER_DESIGN\.hitSize \/ 2, VENUE_MARKER_DESIGN\.hitSize - 2\]/);
  assert.match(mapSource, /icons\[markerSignal\]/);
  assert.match(mapSource, /<MarkerKey \/>/);
  assert.ok(mapSource.indexOf("Classic ground") > -1);
  assert.ok(!mapSource.slice(mapSource.indexOf("markerKeyItems"), mapSource.indexOf("function MarkerKey")).includes('label: "Standard"'));
});

test("selected card reason follows the winning gold marker signal", () => {
  const reasons = [
    { key: "CLASSIC_GROUND", label: "A classic ground" },
    { key: "FOOTBALL_LANDMARK", label: "A football landmark" },
    { key: "SIGNIFICANT_RIVALRY", label: "A significant rivalry" },
  ];
  assert.equal(editorialReasonForMarkerSignal({ fixture_type: "standard", decision_attribute_keys: reasons.map((reason) => reason.key), decision_reasons: reasons })?.label, "A significant rivalry");
  assert.equal(editorialReasonForMarkerSignal({ fixture_type: "cup", decision_attribute_keys: reasons.map((reason) => reason.key), decision_reasons: reasons }), null);
  assert.equal(editorialReasonForMarkerSignal({ fixture_type: "standard", decision_attribute_keys: ["FOOTBALL_LANDMARK", "CLASSIC_GROUND"], decision_reasons: reasons })?.label, "A football landmark");
  assert.equal(editorialReasonForMarkerSignal({ fixture_type: "standard", decision_attribute_keys: ["CLASSIC_GROUND"], decision_reasons: reasons })?.label, "A classic ground");
});
