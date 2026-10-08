import test from "node:test";
import assert from "node:assert/strict";
import { fixtureKickoffConfirmed } from "./fixture-status.ts";

test("unconfirmed, postponed, cancelled and invalid kickoff times are never actionable", () => {
  for (const status of ["TBD", "PST", "CANC", "ABD", null]) assert.equal(fixtureKickoffConfirmed(status, "2026-10-10T14:00:00Z"), false);
  assert.equal(fixtureKickoffConfirmed("NS", "invalid"), false);
  for (const status of ["NS", "FT", "1H"]) assert.equal(fixtureKickoffConfirmed(status, "2026-10-10T14:00:00Z"), true);
  assert.equal(fixtureKickoffConfirmed("NS", ""), false);
});

test("native Intl conversion follows user-zone DST without changing the canonical instant", () => {
  const format=(instant:string, timeZone:string) => new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone }).format(new Date(instant));
  assert.equal(format("2026-10-24T14:00:00Z", "Europe/London"), "15:00");
  assert.equal(format("2026-10-25T14:00:00Z", "Europe/London"), "14:00");
  assert.equal(format("2026-11-01T14:00:00Z", "America/New_York"), "09:00");
  assert.equal(format("2026-10-31T14:00:00Z", "America/New_York"), "10:00");
});
