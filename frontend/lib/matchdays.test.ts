import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { previewItems, trustworthyScore } from "./matchdays.ts";

const matchdaysPage = readFileSync(new URL("../app/components/InterestedTab.tsx", import.meta.url), "utf8");
const navigation = readFileSync(new URL("../app/components/Navigation.tsx", import.meta.url), "utf8");

test("bounds and expands matchday lists", () => {
  assert.deepEqual(previewItems([1, 2, 3, 4], 2, false), [1, 2]);
  assert.deepEqual(previewItems([1, 2, 3, 4], 2, true), [1, 2, 3, 4]);
});

test("shows only complete final scores", () => {
  assert.equal(trustworthyScore({ status: "FT", home_goals: 2, away_goals: 1 }), "2–1");
  assert.equal(trustworthyScore({ status: "NS", home_goals: null, away_goals: null }), null);
  assert.equal(trustworthyScore({ status: "FT", home_goals: 2, away_goals: null }), null);
});

test("matchday occasions use bounded editorial cards with a graceful score fallback", () => {
  assert.match(matchdaysPage, /tt-panel min-w-0 p-4 sm:p-5/);
  assert.match(matchdaysPage, /\{score \?\? "v"\}/);
  assert.match(matchdaysPage, /UPCOMING_PREVIEW_LIMIT/);
  assert.match(matchdaysPage, /ANSWER_PREVIEW_LIMIT/);
  assert.match(matchdaysPage, /PAST_PREVIEW_LIMIT/);
});

test("mobile wordmark is calibrated without changing its desktop width", () => {
  assert.match(navigation, /w-\[7\.75rem\] sm:w-\[10\.5rem\]/);
});
