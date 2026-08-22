import type { Fixture } from "../app/types/fixture";

const TWO_HOURS_MS = 2 * 60 * 60 * 1000;

export function localCalendarDateValue(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

export function normalizeDiscoveryStartDate(
  value: string,
  today = localCalendarDateValue()
) {
  if (!isValidCalendarDate(value)) {
    return value;
  }
  return value < today ? today : value;
}

export function isValidCalendarDate(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));

  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

export function bufferedApiDateBound(
  value: string,
  dayOffset: number
) {
  if (!isValidCalendarDate(value)) return undefined;
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + dayOffset);
  return date.toISOString().slice(0, 10);
}

export function discoveryDateRangeError(startDate: string, endDate: string) {
  if ((startDate && !isValidCalendarDate(startDate)) || (endDate && !isValidCalendarDate(endDate))) {
    return "Enter complete dates in YYYY-MM-DD format.";
  }
  if (startDate && endDate && startDate > endDate) {
    return "Start date must be on or before end date.";
  }
  return null;
}

export type FixtureVenueGroup = {
  key: string;
  venueId: number | null;
  fixtures: Fixture[];
};

export function coordinateDistanceMiles(
  from: { latitude: number; longitude: number },
  to: { latitude: number; longitude: number }
) {
  const radians = (degrees: number) => degrees * Math.PI / 180;
  const earthRadiusMiles = 3958.8;
  const latitudeDelta = radians(to.latitude - from.latitude);
  const longitudeDelta = radians(to.longitude - from.longitude);
  const startLatitude = radians(from.latitude);
  const endLatitude = radians(to.latitude);
  const haversine = Math.sin(latitudeDelta / 2) ** 2
    + Math.cos(startLatitude) * Math.cos(endLatitude) * Math.sin(longitudeDelta / 2) ** 2;

  return 2 * earthRadiusMiles * Math.asin(Math.sqrt(haversine));
}

export function hasMeaningfulMapMovement(
  applied: { latitude: number; longitude: number },
  candidate: { latitude: number; longitude: number },
  radiusMiles: number
) {
  return coordinateDistanceMiles(applied, candidate) >= Math.max(2, radiusMiles * 0.1);
}

export function applyMapAreaOrigin<T extends { latitude: number; longitude: number; locationName: string }>(
  appliedSearch: T,
  liveCenter: { latitude: number; longitude: number }
): T {
  return { ...appliedSearch, ...liveCenter, locationName: "Map area" };
}

export type DiscoveryViewport = {
  center: { latitude: number; longitude: number };
  north: number;
  south: number;
  east: number;
  west: number;
};

export type UserLocation = { latitude: number; longitude: number };
export type UserLocationEvent =
  | { type: "geolocation"; location: UserLocation }
  | { type: "manual-location" | "reset" | "map-moved" };

export function applyUserLocationEvent(
  current: UserLocation | null,
  event: UserLocationEvent,
): UserLocation | null {
  if (event.type === "geolocation") return event.location;
  if (event.type === "map-moved") return current;
  return null;
}

export type DiscoveryRequestFilters = {
  startDate?: string;
  endDate?: string;
  leagueIds: number[];
  limit?: number;
};

export function discoveryZoomForRadius(radiusMiles: number) {
  if (radiusMiles <= 10) return 10;
  if (radiusMiles <= 25) return 8;
  if (radiusMiles <= 50) return 7;
  return 6;
}

export function buildViewportDiscoveryParams(
  viewport: DiscoveryViewport,
  filters: DiscoveryRequestFilters,
) {
  return {
    latitude: viewport.center.latitude,
    longitude: viewport.center.longitude,
    north: viewport.north,
    south: viewport.south,
    east: viewport.east,
    west: viewport.west,
    start_date: filters.startDate,
    end_date: filters.endDate,
    league_id: filters.leagueIds.length ? filters.leagueIds : undefined,
    limit: filters.limit ?? 250,
  };
}

export function isCurrentDiscoveryRequest(currentVersion: number, responseVersion: number) {
  return currentVersion === responseVersion;
}

export function resolvedLocationTransition(
  origin: { latitude: number; longitude: number },
  locationName: string,
  requestVersion: number,
  currentViewportRevision: number,
) {
  return {
    requestVersion,
    locationQuery: locationName,
    draftCoordinates: origin,
    viewportTarget: {
      ...origin,
      revision: currentViewportRevision + 1,
    },
  };
}

export function compactFixtureCard(fixture: Fixture) {
  return {
    matchup: `${fixture.home_team} v ${fixture.away_team}`,
    fixtureDate: fixture.fixture_date,
    status: fixture.status,
    href: `/fixture/${fixture.fixture_id}`,
  };
}

export const FIXTURE_POPUP_BEHAVIOR = {
  autoPan: false,
  autoClose: true,
  closeOnClick: true,
} as const;

export function groupFixturesByVenue(fixtures: Fixture[]): FixtureVenueGroup[] {
  const groups = new Map<string, FixtureVenueGroup>();

  for (const fixture of fixtures) {
    const hasVenueId = fixture.venue_id !== null && Number.isFinite(Number(fixture.venue_id));
    const venueId = hasVenueId ? Number(fixture.venue_id) : null;
    const key = venueId === null ? `fixture:${fixture.fixture_id}` : `venue:${venueId}`;
    const group = groups.get(key) ?? { key, venueId, fixtures: [] };
    group.fixtures.push(fixture);
    groups.set(key, group);
  }

  return Array.from(groups.values()).map((group) => ({
    ...group,
    fixtures: [...group.fixtures].sort(
      (left, right) =>
        new Date(left.fixture_date).getTime() - new Date(right.fixture_date).getTime()
        || left.fixture_id - right.fixture_id
    ),
  }));
}

export function isFixtureDiscoverable(
  fixtureDate: string,
  now = new Date()
) {
  const kickoff = new Date(fixtureDate);

  if (Number.isNaN(kickoff.getTime())) {
    return false;
  }

  const todayStart = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate()
  );
  const fixtureDay = new Date(
    kickoff.getFullYear(),
    kickoff.getMonth(),
    kickoff.getDate()
  );

  if (fixtureDay.getTime() < todayStart.getTime()) {
    return false;
  }

  if (fixtureDay.getTime() > todayStart.getTime()) {
    return true;
  }

  return now.getTime() <= kickoff.getTime() + TWO_HOURS_MS;
}

export function selectDiscoveryFixtures(
  fixtures: Fixture[],
  radius: number,
  now = new Date(),
  startDate?: string,
  endDate?: string,
  applyRadius = true,
) {
  const validStartDate = startDate && isValidCalendarDate(startDate) ? startDate : undefined;
  const validEndDate = endDate && isValidCalendarDate(endDate) ? endDate : undefined;
  return fixtures
    .filter(
      (fixture) => {
        const fixtureCalendarDate = localCalendarDateValue(
          new Date(fixture.fixture_date)
        );

        return (
          (!applyRadius || fixture.distance_miles <= radius) &&
          (!validStartDate || fixtureCalendarDate >= validStartDate) &&
          (!validEndDate || fixtureCalendarDate <= validEndDate) &&
          isFixtureDiscoverable(fixture.fixture_date, now)
        );
      }
    )
    .sort(
      (left, right) =>
        new Date(left.fixture_date).getTime() -
        new Date(right.fixture_date).getTime()
        || left.fixture_id - right.fixture_id
    );
}
