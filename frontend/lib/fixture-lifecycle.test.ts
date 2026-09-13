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
