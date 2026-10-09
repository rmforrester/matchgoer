import test from "node:test";
import assert from "node:assert/strict";
import { formatKickoffTime, formatFixtureDistance } from "./fixture-format.ts";

test("12-hour kickoff preserves zone/DST and canonical instants", () => {
  const date = new Date("2026-10-10T12:15:00Z");
  assert.equal(formatKickoffTime(date, { timeZone: "America/New_York" }), "8:15 AM");
  assert.equal(date.toISOString(), "2026-10-10T12:15:00.000Z");
  assert.equal(formatKickoffTime("2026-10-24T14:00:00Z", { timeZone: "Europe/London" }), "3:00 PM");
  assert.equal(formatKickoffTime("2026-10-25T14:00:00Z", { timeZone: "Europe/London" }), "2:00 PM");
  assert.equal(formatKickoffTime("2026-10-31T14:00:00Z", { timeZone: "America/New_York" }), "10:00 AM");
  assert.equal(formatKickoffTime("2026-11-01T14:00:00Z", { timeZone: "America/New_York" }), "9:00 AM");
  assert.equal(formatKickoffTime("2026-10-10T00:00:00Z", { timeZone: "UTC" }), "12:00 AM");
  assert.equal(formatKickoffTime("2026-10-10T12:00:00Z", { timeZone: "UTC" }), "12:00 PM");
});
test("fixture distance describes the applied search origin without altering miles", () => {
  assert.equal(formatFixtureDistance(4.24, "Stockholm"), "4.2 miles from Stockholm");
  assert.equal(formatFixtureDistance(4.24, "Current location"), "4.2 miles from your current location");
  assert.equal(formatFixtureDistance(4.24), "4.2 miles from the search location");
  assert.equal(formatFixtureDistance(4.24, "Long City Name, Region, Country"), "4.2 miles from Long City Name, Region, Country");
});
