import test from "node:test";
import assert from "node:assert/strict";
import { ticketVisibleOnMatchday as visible } from "./fixture-ticket-visibility.ts";

test("venue-local calendar midnight, independent of viewer zone", () => {
  for (const viewer of ["UTC", "America/Los_Angeles", "Pacific/Auckland"]) {
    const previous = process.env.TZ; process.env.TZ = viewer;
    try {
      // Same kickoff, three European offsets: matchday visibility and next-day cutoff.
      for (const [zone, cutoff] of [["Europe/London", "2026-10-20T23:00:00Z"], ["Europe/Paris", "2026-10-20T22:00:00Z"], ["Europe/Bucharest", "2026-10-20T21:00:00Z"]]) {
        const boundary = Date.parse(cutoff);
        assert.equal(visible("2026-10-20T18:00:00Z", zone, new Date("2026-10-19T12:00:00Z")), true);
        assert.equal(visible("2026-10-20T18:00:00Z", zone, new Date(boundary - 1)), true);
        assert.equal(visible("2026-10-20T18:00:00Z", zone, new Date(boundary)), false);
        assert.equal(visible("2026-10-20T18:00:00Z", zone, new Date("2026-10-22T12:00:00Z")), false);
      }
      // Auckland matchday starts before its UTC date; cutoff is next local midnight.
      assert.equal(visible("2026-10-20T06:00:00Z", "Pacific/Auckland", new Date("2026-10-20T10:59:59Z")), true);
      assert.equal(visible("2026-10-20T06:00:00Z", "Pacific/Auckland", new Date("2026-10-20T11:00:00Z")), false);
      assert.equal(visible("2026-10-21T02:00:00Z", "America/Los_Angeles", new Date("2026-10-21T06:59:59Z")), true);
      assert.equal(visible("2026-10-21T02:00:00Z", "America/Los_Angeles", new Date("2026-10-21T07:00:00Z")), false);
    } finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous; }
  }
});

test("DST spring/fall use the offset at cutoff, not kickoff plus 24 hours", () => {
  for (const [kickoff, boundary] of [["2026-03-29T00:30:00Z", "2026-03-29T22:00:00Z"], ["2026-10-25T00:30:00Z", "2026-10-25T23:00:00Z"]]) {
    const midnight = Date.parse(boundary);
    assert.equal(visible(kickoff, "Europe/Rome", new Date(midnight - 1)), true);
    assert.equal(visible(kickoff, "Europe/Rome", new Date(midnight)), false);
  }
});

test("future matchdays remain visible; unknown or invalid time data fails closed", () => {
  assert.equal(visible("2027-01-01T15:00:00Z", "Europe/London", new Date("2026-12-01T00:00:00Z")), true);
  for (const zone of [null, undefined, "", "invented/zone", "Etc/GMT+5"]) assert.equal(visible("2026-10-20T12:00:00Z", zone), false);
  for (const date of [null, undefined, "invalid", "2026-10-20", "2026-10-20T12:00:00"]) assert.equal(visible(date, "Europe/Rome"), false);
  assert.equal(visible("2026-10-20T12:00:00Z", "Europe/Rome", new Date("invalid")), false);
});
