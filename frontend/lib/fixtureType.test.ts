import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { fixtureTypeLabel, safeFixtureType } from "./fixtureType.ts";

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

test("cup and international selected cards retain one competition-type icon", () => {
  assert.equal((mapSource.match(/<FixtureTypeIcon type=\{fixtureType\}/g) ?? []).length, 2);
});
