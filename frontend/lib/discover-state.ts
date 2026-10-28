import type { Fixture } from "../app/types/fixture";
import type { DiscoveryViewport } from "./fixtureDiscovery";
export type AppliedSearch = {
  latitude: number;
  longitude: number;
  locationName: string;
  radius: number;
  startDate: string;
  endDate: string;
  leagueIds: number[];
  showAllStadiums: boolean;
  mode: "radius" | "viewport";
  totalMatches: number;
  resultsLimited: boolean;
};

type Venue = { venue_id: number; name: string; city: string | null; latitude: number | null; longitude: number | null };
export type DiscoverState = {
  appliedSearch: AppliedSearch | null; fixtures: Fixture[]; venues: Venue[];
  locationQuery: string; draftCoordinates: { latitude: number; longitude: number } | null;
  radius: number; startDate: string; endDate: string; leagueIds: number[];
  showAllStadiums: boolean; editingSearch: boolean;
  mapPosition: { latitude: number; longitude: number; zoom: number } | null;
  selectedFixtureId: number | null; searchArea: DiscoveryViewport | null;
  resultsAt: number; scrollY: number;
};
export const DISCOVER_FRESH_MS = 5 * 60_000;
const KEY = "matchgoer.discover-search.v1";
let memory: DiscoverState | null = null;

// Persist an explicit allowlist of search settings only. Results and selected
// cards remain memory-only, and no account, token or attendance state is stored.
export function writeDiscoverState(state: DiscoverState, storage?: Pick<Storage, "setItem">) {
  memory = state;
  const { appliedSearch, locationQuery, draftCoordinates, radius, startDate, endDate,
    leagueIds, showAllStadiums, editingSearch, mapPosition, searchArea, scrollY } = state;
  try { (storage ?? localStorage).setItem(KEY, JSON.stringify({ version: 1, appliedSearch,
    locationQuery, draftCoordinates, radius, startDate, endDate, leagueIds,
    showAllStadiums, editingSearch, mapPosition, searchArea, scrollY })); } catch { /* In-memory navigation remains available. */ }
}
export function readDiscoverState(storage?: Pick<Storage, "getItem">): DiscoverState | null {
  if (!storage && memory) return memory;
  try {
    const data = JSON.parse((storage ?? localStorage).getItem(KEY) ?? "null");
    const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);
    const point = (p: { latitude?: unknown; longitude?: unknown } | null) => p === null ||
      (p && finite(p.latitude) && Math.abs(p.latitude) <= 90 && finite(p.longitude) && Math.abs(p.longitude) <= 180);
    const ids = (list: unknown) => Array.isArray(list) && list.length <= 500 && list.every(n => Number.isSafeInteger(n) && n > 0);
    const date = (value: unknown) => typeof value === "string" && (value === "" || /^\d{4}-\d{2}-\d{2}$/.test(value));
    if (!data || data.version !== 1 || typeof data.locationQuery !== "string" || data.locationQuery.length > 1000 ||
      !point(data.draftCoordinates) || !finite(data.radius) || data.radius <= 0 || data.radius > 1000 ||
      !date(data.startDate) || !date(data.endDate) || !ids(data.leagueIds) ||
      typeof data.showAllStadiums !== "boolean" || typeof data.editingSearch !== "boolean" ||
      !finite(data.scrollY) || data.scrollY < 0 || !point(data.mapPosition) ||
      (data.mapPosition && (!finite(data.mapPosition.zoom) || data.mapPosition.zoom < 0 || data.mapPosition.zoom > 22))) return null;
    const a = data.appliedSearch;
    if (a && (!point(a) || !date(a.startDate) || !date(a.endDate) || !ids(a.leagueIds) ||
      !finite(a.radius) || a.radius <= 0 || a.radius > 1000 || typeof a.locationName !== "string" ||
      typeof a.showAllStadiums !== "boolean" || !["radius", "viewport"].includes(a.mode))) return null;
    const area = data.searchArea;
    if (area && (!point(area.center) || !area.center || ![area.north, area.south, area.east, area.west].every(finite) ||
      area.north > 90 || area.south < -90 || area.east > 180 || area.west < -180 || area.north < area.south)) return null;
    if (a && !area) return null;
    return { appliedSearch: a, locationQuery: data.locationQuery, draftCoordinates: data.draftCoordinates,
      radius: data.radius, startDate: data.startDate, endDate: data.endDate, leagueIds: data.leagueIds,
      showAllStadiums: data.showAllStadiums, editingSearch: data.editingSearch,
      mapPosition: data.mapPosition, searchArea: area, scrollY: data.scrollY,
      fixtures: [], venues: [], selectedFixtureId: null, resultsAt: 0 };
  } catch { return null; }
}
