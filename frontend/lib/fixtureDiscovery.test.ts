import assert from "node:assert/strict";
import test from "node:test";

import {
  applyMapAreaOrigin,
  buildViewportDiscoveryParams,
  discoveryZoomForRadius,
  isCurrentDiscoveryRequest,
  type DiscoveryViewport,
} from "./fixtureDiscovery.ts";

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
