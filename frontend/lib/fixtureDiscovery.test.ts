import assert from "node:assert/strict";
import test from "node:test";

import {
  applyMapAreaOrigin,
  applyUserLocationEvent,
  beginGeolocationTransition,
  buildViewportDiscoveryParams,
  compactFixtureCard,
  discoveryZoomForRadius,
  endDateAtOrAfterStart,
  FIXTURE_POPUP_BEHAVIOR,
  geolocationErrorMessage,
  GEOLOCATION_INSECURE_MESSAGE,
  GEOLOCATION_UNSUPPORTED_MESSAGE,
  isCurrentDiscoveryRequest,
  manualCurrentLocationOrigin,
  resolvedLocationTransition,
  upcomingWeekendDateRange,
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

test("weekend shortcut selects the upcoming Friday through Sunday on a weekday", () => {
  assert.deepEqual(upcomingWeekendDateRange(new Date(2026, 8, 2, 12)), {
    startDate: "2026-09-04",
    endDate: "2026-09-06",
  });
});

test("weekend shortcut keeps the current Friday through Sunday all weekend", () => {
  assert.deepEqual(upcomingWeekendDateRange(new Date(2026, 8, 4, 12)), {
    startDate: "2026-09-04",
    endDate: "2026-09-06",
  });
  assert.deepEqual(upcomingWeekendDateRange(new Date(2026, 8, 5, 12)), {
    startDate: "2026-09-04",
    endDate: "2026-09-06",
  });
  assert.deepEqual(upcomingWeekendDateRange(new Date(2026, 8, 6, 12)), {
    startDate: "2026-09-04",
    endDate: "2026-09-06",
  });
});

test("manual end date never precedes the chosen start date", () => {
  assert.equal(endDateAtOrAfterStart("2026-12-26", "2026-09-30"), "2026-12-26");
  assert.equal(endDateAtOrAfterStart("2026-12-26", "2026-12-28"), "2026-12-28");
});

test("manual Use my location establishes an origin without choosing dates", () => {
  const origin = { latitude: 53.4106, longitude: -2.1575 };
  assert.deepEqual(manualCurrentLocationOrigin(origin), {
    locationQuery: "Current location",
    draftCoordinates: origin,
    userLocation: origin,
  });
});

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

test("fixture popup auto-pans with padding while preserving normal close behavior", () => {
  assert.deepEqual(FIXTURE_POPUP_BEHAVIOR, {
    autoPan: true,
    keepInView: true,
    autoPanPaddingTopLeft: [56, 72],
    autoPanPaddingBottomRight: [32, 32],
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

test("city search to Use My Location invalidates the city target before requesting position", () => {
  assert.deepEqual(beginGeolocationTransition(11), {
    requestVersion: 12,
    draftCoordinates: null,
    viewportTarget: { latitude: 0, longitude: 0, revision: 0 },
  });
});

test("successful geolocation becomes authoritative and produces a new map target", () => {
  const cityTarget = { latitude: 25.774, longitude: -80.194, revision: 4 };
  const started = beginGeolocationTransition(11);
  const position = { latitude: 51.5074, longitude: -0.1278 };
  const resolved = resolvedLocationTransition(position, "Current location", started.requestVersion, cityTarget.revision);

  assert.deepEqual(resolved.viewportTarget, { ...position, revision: 5 });
  assert.deepEqual(resolved.draftCoordinates, position);
  assert.equal(resolved.locationQuery, "Current location");
});

test("failed geolocation clears the pending target without moving the rendered map", () => {
  const started = beginGeolocationTransition(11);
  const existingMarker = { latitude: 51.5074, longitude: -0.1278 };

  assert.equal(started.viewportTarget.revision, 0);
  assert.deepEqual(applyUserLocationEvent(existingMarker, { type: "map-moved" }), existingMarker);
});

test("PERMISSION_DENIED has concise settings guidance", () => {
  assert.equal(
    geolocationErrorMessage(1),
    "Location access is off. Enable location access or search for a city.",
  );
});

test("POSITION_UNAVAILABLE does not claim permission was denied", () => {
  assert.equal(
    geolocationErrorMessage(2),
    "Couldn’t get your location. Try again or search for a city.",
  );
  assert.notEqual(geolocationErrorMessage(2), geolocationErrorMessage(1));
});

test("TIMEOUT does not claim permission was denied", () => {
  assert.equal(
    geolocationErrorMessage(3),
    "Couldn’t get your location. Try again or search for a city.",
  );
  assert.notEqual(geolocationErrorMessage(3), geolocationErrorMessage(1));
});

test("unsupported and insecure-context fallbacks remain distinct", () => {
  assert.equal(GEOLOCATION_UNSUPPORTED_MESSAGE, "Location isn’t available in this browser. Search for a city.");
  assert.equal(GEOLOCATION_INSECURE_MESSAGE, "Use HTTPS for current location, or search for a city.");
});
