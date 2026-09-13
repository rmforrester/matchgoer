import assert from "node:assert/strict";
import test from "node:test";
import { previewItems, trustworthyScore } from "./matchdays.ts";

test("bounds and expands matchday lists", () => {
  assert.deepEqual(previewItems([1, 2, 3, 4], 2, false), [1, 2]);
  assert.deepEqual(previewItems([1, 2, 3, 4], 2, true), [1, 2, 3, 4]);
});

test("shows only complete final scores", () => {
  assert.equal(trustworthyScore({ status: "FT", home_goals: 2, away_goals: 1 }), "2–1");
  assert.equal(trustworthyScore({ status: "NS", home_goals: null, away_goals: null }), null);
  assert.equal(trustworthyScore({ status: "FT", home_goals: 2, away_goals: null }), null);
});
