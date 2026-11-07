import { autocompleteParameters } from "./location-autocomplete.ts";
import { competitionsForGrounds } from "./football-footprint.ts";
import type { MyGround, FootprintCompetition } from "../app/types/grounds.ts";
import test from "node:test";
import assert from "node:assert/strict";
import { coordinatePlaceUrl, placeUrlFromVerifiedUrl } from "./map-destination.ts";
import { resetDiscoverSession, setDiscoverIdentity, discoverCacheRevision, writeDiscoverState, readDiscoverState, type DiscoverState } from "./discover-state.ts";

test("ordinary coordinate links open exact Apple/Google destinations without routes", () => {
  for (const platform of ["apple", "google"] as const) {
    const url = new URL(coordinatePlaceUrl(40.923, -74.174, "Hinchliffe Stadium", platform)!);
    assert.equal(url.searchParams.get(platform === "apple" ? "coordinate" : "query"), "40.923,-74.174");
    for (const key of ["destination", "origin", "saddr", "daddr", "travelmode", "dirflg"]) assert.equal(url.searchParams.has(key), false);
    assert.equal(url.pathname.includes("dir"), false);
    if (platform === "apple") assert.equal(url.searchParams.get("name"), "Hinchliffe Stadium");
  }
});
test("converted coordinate pins retain their destination label on Apple", () => {
  const url = new URL(placeUrlFromVerifiedUrl("https://www.google.com/maps/search/?api=1&query=51.5%2C-0.1", "apple", "Verified Ground")!);
  assert.equal(url.searchParams.get("name"), "Verified Ground");
});
test("missing, non-finite and out-of-range coordinates never substitute a nearby place", () => {
  for (const [lat, lon] of [[0, 0], [NaN, 1], [1, Infinity], [91, 1], [1, -181]]) assert.equal(coordinatePlaceUrl(lat, lon), null);
  assert.equal(placeUrlFromVerifiedUrl(null), null);
  for (const url of ["javascript:alert(1)", "https://evil.test/maps/search/?query=Ground", "https://www.google.com/maps/", "https://user:pass@www.google.com/maps/search/?query=Ground"]) assert.equal(placeUrlFromVerifiedUrl(url), null);
});
test("verified pub, cafe, restaurant and meeting-point targets preserve their exact address", () => {
  for (const name of ["Supporters Pub", "Matchday Cafe", "The Restaurant", "Supporters Meeting Point"]) {
    const query = `${name}, 10 Example Street, Test City`;
    const source = `https://www.google.com/maps/search/?${new URLSearchParams({ api: "1", query })}`;
    for (const platform of ["apple", "google"] as const) {
      const dest = new URL(placeUrlFromVerifiedUrl(source, platform)!);
      assert.equal(dest.searchParams.get(platform === "apple" ? "address" : "query"), query);
      assert.equal(dest.searchParams.has("destination"), false);
    }
  }
});
test("Google place IDs are retained on Apple rather than guessed into a different identity", () => {
  const source = "https://www.google.com/maps/search/?api=1&query=Verified+Place&query_place_id=verified-id";
  const url = new URL(placeUrlFromVerifiedUrl(source, "apple")!);
  assert.equal(url.hostname, "www.google.com"); assert.equal(url.searchParams.get("query_place_id"), "verified-id");
});
test("legacy route URLs are converted to destination-only place views", () => {
  for (const platform of ["apple", "google"] as const) {
    const url = new URL(placeUrlFromVerifiedUrl("https://www.google.com/maps/dir/?api=1&destination=51.5%2C-0.1&origin=private&travelmode=driving", platform)!);
    assert.equal(url.searchParams.get(platform === "apple" ? "coordinate" : "query"), "51.5,-0.1");
    assert.equal(url.searchParams.has("origin"), false);assert.equal(url.searchParams.has("travelmode"), false);
  }
});

test("logout reset invalidates stale writes and clears only transient Discover storage", () => {
  const values = new Map<string, string>([["saved-interest", "keep"], ["account-preference", "keep"], ["supabase-session", "keep"]]);
  const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key,value); }, removeItem: (key: string) => { values.delete(key); } };
  const snapshot = { appliedSearch: null, fixtures: [], venues: [], locationQuery: "Map area", draftCoordinates: null, radius: 25, startDate: "", endDate: "", leagueIds: [7001], showAllStadiums: true, editingSearch: true, mapPosition: null, selectedFixtureId: 91, searchArea: null, resultsAt: Date.now(), scrollY: 0 } satisfies DiscoverState;
  const old = discoverCacheRevision();writeDiscoverState(snapshot,storage,old);assert.ok(storage.getItem("matchgoer.discover-search.v1"));
  resetDiscoverSession(storage);assert.equal(readDiscoverState(),null);assert.equal(storage.getItem("matchgoer.discover-search.v1"),null);
  writeDiscoverState(snapshot,storage,old);assert.equal(storage.getItem("matchgoer.discover-search.v1"),null);
  assert.equal(storage.getItem("saved-interest"),"keep");assert.equal(storage.getItem("account-preference"),"keep");assert.equal(storage.getItem("supabase-session"),"keep");
});
test("account changes and same-account logout/login reset, stable same-session refresh does not", () => {
  setDiscoverIdentity("admin");const admin=discoverCacheRevision();setDiscoverIdentity("admin");assert.equal(discoverCacheRevision(),admin);
  setDiscoverIdentity("supporter");assert.ok(discoverCacheRevision()>admin);const supporter=discoverCacheRevision();
  setDiscoverIdentity(null,true);setDiscoverIdentity("supporter");assert.ok(discoverCacheRevision()>supporter);
});

test("removing the last visit for one competition immediately removes only that classification", () => {
  const league = { competition_id: 1, grounds: [{ venue_id: 9, clubs: [], visit_ids: [1], season_visit_ids: [1] }] } as unknown as FootprintCompetition;
  const cup = { competition_id: 2, grounds: [{ venue_id: 9, clubs: [], visit_ids: [2], season_visit_ids: [2] }] } as unknown as FootprintCompetition;
  const grounds = [{ venue_id: 9, visits: [{ visit_id: 2, fixture_id: 20, visit_date: "2026-10-24" }] }] as MyGround[];
  assert.deepEqual(competitionsForGrounds([league,cup],grounds,"lifetime").map(c => c.competition_id),[2]);
  assert.equal(league.grounds[0].visit_ids?.length,1);
});
test("a single physical ground can classify two attended competitions without mutating visit totals", () => {
  const grounds = [{ venue_id: 9, visits: [{ visit_id: 1, fixture_id: 10, visit_date: "2026-10-24" },{ visit_id: 2, fixture_id: 20, visit_date: "2026-10-25" }] }] as MyGround[];
  const comps = [1,2].map(id => ({ competition_id: id, grounds: [{ venue_id: 9, clubs: [], visit_ids: [id], season_visit_ids: [id] }] })) as unknown as FootprintCompetition[];
  const before=structuredClone(grounds);assert.equal(competitionsForGrounds(comps,grounds,"lifetime").length,2);assert.deepEqual(grounds,before);
});
test("ground-only membership cannot retain stale competition classifications", () => {
  const comps=[{ competition_id:1,grounds:[{venue_id:9,clubs:[],visit_ids:[1],season_visit_ids:[1]}] }] as unknown as FootprintCompetition[];
  const grounds=[{ venue_id:9,independently_saved:true,visits:[] }] as unknown as MyGround[];
  assert.deepEqual(competitionsForGrounds(comps,grounds,"lifetime"),[]);assert.deepEqual(competitionsForGrounds(comps,[],"lifetime"),[]);
});

test("the Map area display sentinel is never sent to city autocomplete", () => {
  for (const value of ["Map area", " map AREA "]) assert.equal(autocompleteParameters(value),null);
  assert.equal(autocompleteParameters("Berlin")?.get("text"),"Berlin");
});
