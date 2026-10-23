import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { previewItems, trustworthyScore, canConfirmAttendance, partitionMatchdays, formatMatchdayKickoff, reconcileGoingRead, type ConfirmedGoing } from "./matchdays.ts";

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
  assert.match(matchdaysPage, /FixtureTeams compact/);
  assert.match(matchdaysPage, /UPCOMING_PREVIEW_LIMIT/);
  assert.match(matchdaysPage, /PAST_PREVIEW_LIMIT/);
});

test("mobile wordmark is calibrated without changing its desktop width", () => {
  assert.match(navigation, /w-\[7\.75rem\] sm:w-\[10\.5rem\]/);
});

const kickoff = "2026-10-10T14:00:00Z";
const saved = (id: number, going = false, status = "NS") => ({ fixture_id: id, fixture_date: kickoff, going, status, venue_id: 9 });
test("Going acknowledgement protects one conflicting read then confirms a fresh matching read", () => {
  const fixture = saved(1);
  const confirmations = new Map<number, ConfirmedGoing<typeof fixture>>([[1, { fixture, going: true, checked: false }]]);
  const stale = reconcileGoingRead([saved(1)], confirmations);
  assert.equal(stale.rows[0].going, true); assert.deepEqual(stale.retry, [1]);
  const fresh = reconcileGoingRead([saved(1, true)], confirmations);
  assert.equal(fresh.rows[0].going, true); assert.equal(confirmations.size, 0);
  assert.equal(reconcileGoingRead([saved(1, false)], confirmations).rows[0].going, false);
});
test("reversal protects against old true and genuine subsequent differences are bounded", () => {
  const fixture = saved(1, true);
  const confirmations = new Map<number, ConfirmedGoing<typeof fixture>>([[1, { fixture, going: false, checked: false }]]);
  assert.equal(reconcileGoingRead([fixture], confirmations).rows[0].going, false);
  const newer = reconcileGoingRead([fixture], confirmations);
  assert.equal(newer.rows[0].going, true); assert.deepEqual(newer.changed, [1]); assert.equal(confirmations.size, 0);
});
test("missing stale row is protected once but a confirmed removal is not masked forever", () => {
  const fixture = saved(1);
  const confirmations = new Map<number, ConfirmedGoing<typeof fixture>>([[1, { fixture, going: true, checked: false }]]);
  assert.equal(reconcileGoingRead([], confirmations).rows[0].fixture_id, 1);
  assert.deepEqual(reconcileGoingRead([], confirmations).rows, []);
});
test("attendance confirmation requires completed status, a canonical venue and a past kickoff", () => {
  const now = new Date("2026-10-10T17:00:00Z");
  for (const status of ["FT", "AET", "PEN"]) assert.equal(canConfirmAttendance(saved(1, false, status), now), true);
  for (const status of ["NS", "TBD", "", "PST", "CANC", "ABD", "AWD", "WO", "1H", "HT", "2H", "ET", "P", "LIVE", "SUSP", "INT"]) assert.equal(canConfirmAttendance(saved(1, false, status), now), false);
  assert.equal(canConfirmAttendance(saved(1, false, "FT"), new Date("2026-10-10T13:59:59Z")), false);
  assert.equal(canConfirmAttendance({ ...saved(1, false, "FT"), fixture_date: "invalid" }, now), false);
  assert.equal(canConfirmAttendance({ ...saved(1, false, "FT"), venue_id: null }, now), false);
});

test("sections are exclusive, Went wins, Going is prioritized and retained plans remain accessible", () => {
  const result = partitionMatchdays([saved(1, false, "FT"), saved(2, true, "FT"), saved(3, true, "FT"), saved(4, true, "PST"), saved(1, false, "FT")], new Set([3]), new Date("2026-10-10T17:00:00Z"));
  assert.deepEqual(result.awaiting.map(f => f.fixture_id), [2, 1]);
  assert.deepEqual(result.going.map(f => f.fixture_id), [4]);
  assert.equal(result.interested.length, 0);
  const upcoming = partitionMatchdays([saved(1), saved(2, true)], new Set(), new Date("2026-10-10T10:00:00Z"));
  assert.deepEqual(upcoming.going.map(f => f.fixture_id), [2]);
  assert.deepEqual(upcoming.interested.map(f => f.fixture_id), [1]);
});
test("confirmation preserves saves, decline alone deletes and old backend hides Going controls", () => {
  assert.match(matchdaysPage, /if \(!attended\) await api\.delete/);
  assert.match(matchdaysPage, /typeof fixture\.going === "boolean"/);
  assert.match(matchdaysPage, /View match/);
});

test("My Matchdays formats noon, midnight and evening in twelve-hour local time", () => {
  assert.deepEqual(formatMatchdayKickoff("2026-10-10T12:30:00Z", "UTC"), { date: "Sat 10 Oct", time: "12:30 PM" });
  assert.equal(formatMatchdayKickoff("2026-10-10T00:00:00Z", "UTC").time, "12:00 AM");
  assert.equal(formatMatchdayKickoff("2026-10-10T19:00:00Z", "UTC").time, "7:00 PM");
  assert.equal(formatMatchdayKickoff("2026-10-10T14:45:00Z", "UTC").time, "2:45 PM");
});
test("My Matchdays keeps the same instant across timezones and daylight-saving changes", () => {
  assert.equal(formatMatchdayKickoff("2026-10-10T12:30:00Z", "America/New_York").time, "8:30 AM");
  assert.equal(formatMatchdayKickoff("2026-11-01T05:30:00Z", "America/New_York").time, "1:30 AM");
  assert.equal(formatMatchdayKickoff("2026-11-01T06:30:00Z", "America/New_York").time, "1:30 AM");
  assert.equal(formatMatchdayKickoff("2026-03-08T06:30:00Z", "America/New_York").time, "1:30 AM");
  assert.equal(formatMatchdayKickoff("2026-03-08T07:30:00Z", "America/New_York").time, "3:30 AM");
});

test("unconfirmed old saves stay in plans; completed and attended fixtures never duplicate sections", () => {
 const rows = [saved(1), saved(2, true), saved(3, false, "FT"), saved(4, true, "FT"), saved(5, true, "FT"), saved(3, false, "FT")];
 const groups = partitionMatchdays(rows, new Set([5]), new Date("2026-10-12T00:00:00Z"));
 assert.deepEqual(groups.interested.map(f => f.fixture_id), [1]);
 assert.deepEqual(groups.going.map(f => f.fixture_id), [2]);
 assert.deepEqual(groups.awaiting.map(f => f.fixture_id), [4,3]);
 const all = [...groups.going, ...groups.interested, ...groups.awaiting];
 assert.equal(all.length, new Set(all.map(f => f.fixture_id)).size);
 const completed = partitionMatchdays([{ ...saved(1), status: "FT" }], new Set(), new Date("2026-10-12T00:00:00Z"));
 assert.equal(completed.interested.length, 0);assert.equal(completed.awaiting.length, 1);
 assert.equal(partitionMatchdays(rows, new Set([3,4,5]), new Date("2026-10-12T00:00:00Z")).awaiting.length, 0);
});
