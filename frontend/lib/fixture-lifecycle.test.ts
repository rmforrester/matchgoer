import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { fixtureHasFinishedForSocial } from "./fixture-status.ts";

const fixturePage = readFileSync(new URL("../app/fixture/[fixtureId]/page.tsx", import.meta.url), "utf8");
const venuePage = readFileSync(new URL("../app/venue/[venueId]/page.tsx", import.meta.url), "utf8");

test("upcoming fixture keeps pre-match social controls", () => {
  assert.equal(fixtureHasFinishedForSocial("NS", false), false);
});

test("finished fixture hides pre-match social controls", () => {
  assert.equal(fixtureHasFinishedForSocial("FT", true), true);
  assert.equal(fixtureHasFinishedForSocial("NS", true), true);
});

test("cancelled fixture retains its dedicated match-update state", () => {
  assert.equal(fixtureHasFinishedForSocial("CANC", true), false);
});

test("fixture page hides Make It Yours after finish and leaves Match Board closure authoritative", () => {
  assert.match(fixturePage, /: !finishedForSocial \? <section/);
  assert.match(fixturePage, /data\.board_closed \? <div/);
});

test("attended personal block follows the venue hero while unattended hierarchy remains separate", () => {
  const hero = venuePage.indexOf("<VenueHeader");
  const attended = venuePage.indexOf("{hasVisited && <>");
  const guide = venuePage.indexOf("{guide && <VenueGuide");
  const unattended = venuePage.indexOf("{!hasVisited && <section");
  assert.ok(hero > -1 && hero < attended && attended < guide && guide < unattended);
  assert.match(venuePage, /tt-panel mt-4 p-4 sm:p-5/);
});

// Fixture-page attendance requires authoritative completion, not board closure.
test("completed attendance handoff excludes uncertain and retained plans", async () => {
  const { canRecordCompletedFixture } = await import("./fixture-status.ts");
  for (const status of ["FT", "AET", "PEN", "ft"]) assert.equal(canRecordCompletedFixture(status, 9), true);
  for (const status of ["NS", "TBD", "1H", "HT", "2H", "ET", "P", "PST", "CANC", "ABD", "AWD", "WO", "SUSP", "INT", "LIVE", "", null, undefined]) {
    assert.equal(canRecordCompletedFixture(status, 9), false, String(status));
  }
  for (const venue of [null, 0, -1, 1.5, NaN]) assert.equal(canRecordCompletedFixture("FT", venue), false);
});

test("retained status messages preserve uncertainty and saved intentions", async () => {
  const { retainedMatchMessage } = await import("./fixture-status.ts");
  assert.equal(retainedMatchMessage("PST"), "This match has been postponed. Your saved match has been kept.");
  assert.equal(retainedMatchMessage("canc"), "This match has been cancelled. Your saved match has been kept.");
  assert.equal(retainedMatchMessage("ABD"), "This match was abandoned. Your saved match has been kept.");
  assert.equal(retainedMatchMessage("AWD", false), "This match was awarded.");
  assert.equal(retainedMatchMessage("WO", false), "This match was decided by a walkover.");
  for (const status of ["FT", "NS", "LIVE", null]) assert.equal(retainedMatchMessage(status), null);
});
