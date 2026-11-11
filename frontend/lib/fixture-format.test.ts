import test from "node:test";
import assert from "node:assert/strict";
import { formatFixtureDate, formatKickoffTime, formatFixtureDistance } from "./fixture-format.ts";

test("contextual dates follow device calendar across UTC midnight and retain time", () => {
  const previous = process.env.TZ; process.env.TZ = "America/New_York";
  try {
    const now = new Date("2026-11-10T23:30:00-05:00");
    assert.equal(formatFixtureDate("2026-11-11T04:45:00Z", now), "TODAY");
    assert.equal(formatKickoffTime("2026-11-11T04:45:00Z"), "11:45 PM");
    assert.equal(formatFixtureDate("2026-11-11T05:00:00Z", now), "TOMORROW");
    assert.equal(formatFixtureDate("2026-11-11T05:00:00Z", new Date("2026-11-11T05:00:00Z")), "TODAY");
    assert.doesNotMatch(formatFixtureDate("2026-11-09T17:00:00Z", now), /TODAY|TOMORROW/);
  } finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous; }
});

test("tomorrow is a calendar operation through month/year boundaries and DST", () => {
  const previous = process.env.TZ; process.env.TZ = "America/New_York";
  try {
    for (const [now, kickoff] of [
      ["2026-01-31T23:30:00-05:00", "2026-02-01T22:00:00-05:00"],
      ["2026-12-31T23:30:00-05:00", "2027-01-01T22:00:00-05:00"],
      ["2026-03-07T23:30:00-05:00", "2026-03-08T23:45:00-04:00"],
      ["2026-10-31T23:30:00-04:00", "2026-11-01T23:45:00-05:00"],
    ]) assert.equal(formatFixtureDate(kickoff, new Date(now)), "TOMORROW");
    assert.equal(formatFixtureDate("2026-11-11T02:00:00Z", new Date("2026-11-10T20:00:00-05:00"), { timeZone: "UTC" }), "TOMORROW");
    assert.equal(formatFixtureDate("invalid"), "Date to be confirmed");
  } finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous; }
});

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
