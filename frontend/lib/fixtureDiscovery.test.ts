import assert from "node:assert/strict";
import test from "node:test";

import {
  applyMapAreaOrigin,
  applyUserLocationEvent,
  buildViewportDiscoveryParams,
  compactFixtureCard,
  discoveryZoomForRadius,
  FIXTURE_POPUP_BEHAVIOR,
  isCurrentDiscoveryRequest,
  resolvedLocationTransition,
  type DiscoveryViewport,
} from "./fixtureDiscovery.ts";
import { USER_MARKER_DESIGN, VENUE_MARKER_DESIGN, venueMarkerPresentation } from "./mapMarkerDesign.ts";

const miamiViewport: DiscoveryViewport = {
  center: { latitude: 25.7741566, longitude: -80.1935973 },
  north: 26.3241566,
  south: 25.2241566,
  east: -79.4435973,
  west: -80.9435973,
};

test("resolved location immediately builds the viewport discovery request without a movement event", () => {
  const params = buildViewportDiscoveryParams(miamiViewport, {
    startDate: "2026-08-20",
    endDate: "2026-10-01",
    leagueIds: [],
  });

  assert.deepEqual(params, {
    latitude: 25.7741566,
    longitude: -80.1935973,
    north: 26.3241566,
    south: 25.2241566,
    east: -79.4435973,
    west: -80.9435973,
    start_date: "2026-08-20",
    end_date: "2026-10-01",
    league_id: undefined,
    limit: 250,
  });
});

test("location and Search This Area use equivalent requests for equivalent viewport coordinates", () => {
  const filters = {
    startDate: "2026-08-20",
    endDate: "2026-10-01",
    leagueIds: [253, 71],
  };

  assert.deepEqual(
    buildViewportDiscoveryParams({ ...miamiViewport }, filters),
    buildViewportDiscoveryParams({ ...miamiViewport }, filters),
  );
});

test("Search This Area keeps the live map center instead of the previous searched location", () => {
  const previous = { latitude: 25.7741566, longitude: -80.1935973, locationName: "Miami", radius: 25 };
  const liveCenter = { latitude: 25.81, longitude: -80.16 };

  assert.deepEqual(applyMapAreaOrigin(previous, liveCenter), {
    latitude: 25.81,
    longitude: -80.16,
    locationName: "Map area",
    radius: 25,
  });
});

test("viewport requests preserve date and league filters", () => {
  const params = buildViewportDiscoveryParams(miamiViewport, {
    startDate: "2026-08-25",
    endDate: "2026-09-02",
    leagueIds: [253],
    limit: 100,
  });

  assert.equal(params.start_date, "2026-08-25");
  assert.equal(params.end_date, "2026-09-02");
  assert.deepEqual(params.league_id, [253]);
  assert.equal(params.limit, 100);
});

test("only the newest discovery request may apply its result", () => {
  assert.equal(isCurrentDiscoveryRequest(8, 8), true);
  assert.equal(isCurrentDiscoveryRequest(8, 7), false);
});

test("selected radius controls the initial map scale before its viewport is searched", () => {
  assert.equal(discoveryZoomForRadius(10), 10);
  assert.equal(discoveryZoomForRadius(25), 8);
  assert.equal(discoveryZoomForRadius(50), 7);
  assert.equal(discoveryZoomForRadius(100), 6);
});

test("manual city discovery is built from the resolved city viewport", () => {
  const params = buildViewportDiscoveryParams(miamiViewport, {
    startDate: "2026-08-20",
    endDate: "2026-10-01",
    leagueIds: [253],
  });
  assert.equal(params.latitude, miamiViewport.center.latitude);
  assert.equal(params.longitude, miamiViewport.center.longitude);
});

test("Use My Location replaces the previous city target and advances the viewport", () => {
  const currentLocation = { latitude: 51.5074, longitude: -0.1278 };
  const transition = resolvedLocationTransition(currentLocation, "Current location", 12, 4);

  assert.deepEqual(transition, {
    requestVersion: 12,
    locationQuery: "Current location",
    draftCoordinates: currentLocation,
    viewportTarget: { ...currentLocation, revision: 5 },
  });
  assert.notDeepEqual(transition.draftCoordinates, miamiViewport.center);
});

test("current-location bounds replace previous city bounds while preserving filters", () => {
  const londonViewport: DiscoveryViewport = {
    center: { latitude: 51.5074, longitude: -0.1278 },
    north: 51.7,
    south: 51.3,
    east: 0.1,
    west: -0.35,
  };
  const params = buildViewportDiscoveryParams(londonViewport, {
    startDate: "2026-08-25",
    endDate: "2026-09-02",
    leagueIds: [39, 40],
  });

  assert.deepEqual(params, {
    latitude: 51.5074,
    longitude: -0.1278,
    north: 51.7,
    south: 51.3,
    east: 0.1,
    west: -0.35,
    start_date: "2026-08-25",
    end_date: "2026-09-02",
    league_id: [39, 40],
    limit: 250,
  });
});

test("a stale city response cannot overwrite the newer geolocation action", () => {
  assert.equal(isCurrentDiscoveryRequest(12, 11), false);
  assert.equal(isCurrentDiscoveryRequest(12, 12), true);
});

test("Search This Area after geolocation uses the live viewport", () => {
  const geolocationSearch = { latitude: 51.5074, longitude: -0.1278, locationName: "Current location", radius: 25 };
  const liveCenter = { latitude: 51.52, longitude: -0.09 };
  assert.deepEqual(applyMapAreaOrigin(geolocationSearch, liveCenter), {
    latitude: 51.52,
    longitude: -0.09,
    locationName: "Map area",
    radius: 25,
  });
});

test("compact fixture card exposes only matchup, timing source, status and link", () => {
  const fixture = {
    fixture_id: 1561634,
    fixture_date: "2026-08-29T15:00:00Z",
    home_team: "Hutnik Kraków",
    away_team: "Stal Stalowa Wola",
    status: "NS",
    home_goals: null,
    away_goals: null,
    league_id: 109,
    league_name: "II Liga",
    venue_id: 22950,
    venue_name: "Stadion Suche Stawy",
    venue_city: "Kraków",
    latitude: 50.066111,
    longitude: 20.057222,
    distance_miles: 5.38,
    away_day_score: null,
    atmosphere_score: null,
    review_count: 0,
    recommend_percentage: null,
    open_to_meet_count: 0,
  };

  assert.deepEqual(compactFixtureCard(fixture), {
    matchup: "Hutnik Kraków v Stal Stalowa Wola",
    fixtureDate: "2026-08-29T15:00:00Z",
    status: "NS",
    href: "/fixture/1561634",
  });
});

test("fixture-card dismissal and replacement never recenter the map", () => {
  assert.deepEqual(FIXTURE_POPUP_BEHAVIOR, {
    autoPan: false,
    autoClose: true,
    closeOnClick: true,
  });
});

test("successful geolocation creates and updates the genuine user marker", () => {
  const london = { latitude: 51.5074, longitude: -0.1278 };
  const updated = { latitude: 51.508, longitude: -0.126 };
  assert.deepEqual(applyUserLocationEvent(null, { type: "geolocation", location: london }), london);
  assert.deepEqual(applyUserLocationEvent(london, { type: "geolocation", location: updated }), updated);
});

test("manual location search clears the user marker", () => {
  const london = { latitude: 51.5074, longitude: -0.1278 };
  assert.equal(applyUserLocationEvent(london, { type: "manual-location" }), null);
});

test("map movement cannot move the genuine user marker", () => {
  const london = { latitude: 51.5074, longitude: -0.1278 };
  assert.deepEqual(applyUserLocationEvent(london, { type: "map-moved" }), london);
});

test("venue markers are visually smaller while retaining a usable hit target", () => {
  const marker = venueMarkerPresentation(false, false);
  assert.deepEqual(marker, { visited: false, selected: false, visibleWidth: 24, visibleHeight: 29, hitSize: 44 });
  assert.equal(VENUE_MARKER_DESIGN.hitSize, 44);
  assert.equal(USER_MARKER_DESIGN.visibleSize, 16);
});

test("selected and visited venue marker states remain identifiable", () => {
  const selected = venueMarkerPresentation(false, true);
  const visited = venueMarkerPresentation(true, false);
  const selectedVisited = venueMarkerPresentation(true, true);
  assert.equal(selected.visibleWidth, 28);
  assert.equal(selected.visibleHeight, 34);
  assert.equal(visited.visited, true);
  assert.equal(selectedVisited.visited, true);
  assert.equal(selectedVisited.selected, true);
  assert.equal(selected.hitSize, 44);
});
