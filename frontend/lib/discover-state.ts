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
  whatsOnExpanded?: boolean; shortlistExpanded?: boolean;
};
export const DISCOVER_FRESH_MS = 5 * 60_000;
export const DISCOVER_IDLE_MS = 30 * 60_000;
export const discoverExpiredEvent = "matchgoer-discover-expired";
const ACTIVITY_KEY = "matchgoer.discover-activity.v1";
type ActivityStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
let lastActivityAt = 0;
let revision = 0;
export function discoverCacheRevision() { return revision; }
function browserStorage(): ActivityStorage | null {
  try { return typeof window === "undefined" ? null : window.localStorage; } catch { return null; }
}
// Only the two public Discover keys are ever removed. Auth/guest ownership and
// saved fixtures/grounds are intentionally outside this cache's lifecycle.
export function expireDiscoverIfInactive(now = Date.now(), storage = browserStorage()) {
  let timestamp = lastActivityAt, hasCache = memory !== null;
  try {
    if (storage) {
      const raw = storage.getItem(ACTIVITY_KEY);
      timestamp = raw === null ? 0 : Number(raw);
      hasCache ||= storage.getItem(KEY) !== null;
    }
  } catch { /* With blocked storage, use the current document's clock. */ }
  if (Number.isFinite(timestamp) && timestamp > 0 && timestamp <= now && now - timestamp < DISCOVER_IDLE_MS) {
    lastActivityAt = timestamp; return false;
  }
  if (!hasCache) return false;
  memory = null; lastActivityAt = 0; revision += 1;
  try { storage?.removeItem(KEY); storage?.removeItem(ACTIVITY_KEY); } catch { /* In-memory reset still works. */ }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(discoverExpiredEvent));
  return true;
}
export function recordDiscoverActivity(now = Date.now(), storage = browserStorage()) {
  // Check before touching the clock: returning after the deadline must not revive
  // an expired search. No event coordinates, keys, text or identity are collected.
  expireDiscoverIfInactive(now, storage);
  lastActivityAt = now;
  try { storage?.setItem(ACTIVITY_KEY, String(now)); } catch { /* Memory-only continuity remains available. */ }
}
export function watchDiscoverActivity() {
  let timer: number;
  const schedule = () => { window.clearTimeout(timer); timer = window.setTimeout(() => {
    if (document.visibilityState !== "hidden") expireDiscoverIfInactive();
  }, Math.max(1, DISCOVER_IDLE_MS - (Date.now() - lastActivityAt))); };
  const activity = () => { if (document.visibilityState === "hidden") return; recordDiscoverActivity(); schedule(); };
  const returning = () => { if (document.visibilityState !== "hidden") activity(); };
  const stored = (event: StorageEvent) => {
    if (event.key === KEY && event.newValue === null) {
      memory = null; lastActivityAt = 0; revision += 1; window.dispatchEvent(new Event(discoverExpiredEvent));
    }
    if (event.key === ACTIVITY_KEY) { expireDiscoverIfInactive(); schedule(); }
  };
  activity();
  const inputs = ["pointerdown", "keydown", "wheel", "touchstart"];
  inputs.forEach(name => window.addEventListener(name, activity, { passive: true }));
  window.addEventListener("focus", returning); window.addEventListener("pageshow", returning);
  document.addEventListener("visibilitychange", returning); window.addEventListener("storage", stored);
  return () => { window.clearTimeout(timer); inputs.forEach(name => window.removeEventListener(name, activity));
    window.removeEventListener("focus", returning); window.removeEventListener("pageshow", returning);
    document.removeEventListener("visibilitychange", returning); window.removeEventListener("storage", stored); };
}
const KEY = "matchgoer.discover-search.v1";
let memory: DiscoverState | null = null;

// Persist an explicit allowlist of search settings only. Results and selected
// cards remain memory-only, and no account, token or attendance state is stored.
export function writeDiscoverState(state: DiscoverState, storage?: Pick<Storage, "setItem">, expectedRevision = revision) {
  if (expectedRevision !== revision) return; // Ignore cleanup/in-flight work from an expired screen.
  if (!lastActivityAt) lastActivityAt = Date.now();
  memory = state;
  const { appliedSearch, locationQuery, draftCoordinates, radius, startDate, endDate,
    leagueIds, showAllStadiums, editingSearch, mapPosition, searchArea, scrollY, whatsOnExpanded = false, shortlistExpanded = false } = state;
  try {
    const target = storage ?? localStorage;
    if ("getItem" in target && typeof target.getItem === "function") {
      const other = Number(target.getItem(ACTIVITY_KEY));
      if (Number.isFinite(other) && other <= Date.now()) lastActivityAt = Math.max(lastActivityAt, other);
    }
    target.setItem(ACTIVITY_KEY, String(lastActivityAt)); target.setItem(KEY, JSON.stringify({ version: 1, appliedSearch,
    locationQuery, draftCoordinates, radius, startDate, endDate, leagueIds,
    showAllStadiums, editingSearch, mapPosition, searchArea, scrollY, whatsOnExpanded, shortlistExpanded })); } catch { /* In-memory navigation remains available. */ }
}
export function readDiscoverState(storage?: Pick<Storage, "getItem">): DiscoverState | null {
  if (expireDiscoverIfInactive(Date.now(), storage ? { getItem: key => storage.getItem(key), setItem: () => {}, removeItem: () => {} } : browserStorage())) return null;
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
    if ([data.whatsOnExpanded, data.shortlistExpanded].some(value => value !== undefined && typeof value !== "boolean")) return null;
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
      whatsOnExpanded: data.whatsOnExpanded ?? false, shortlistExpanded: data.shortlistExpanded ?? false,
      fixtures: [], venues: [], selectedFixtureId: null, resultsAt: 0 };
  } catch { return null; }
}
