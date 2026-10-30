"use client";

import { useAuth } from "./components/AuthProvider";
import TerracePublicGallery from "./components/TerracePublicGallery";

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import axios from "axios";
import api from "../lib/api";
import { apiErrorMessage } from "../lib/api-error";
import { trackEvent, resultBucket } from "../lib/analytics";
import dynamic from "next/dynamic";

import SearchBar from "./components/SearchBar";
import LocationAutocomplete from "./components/LocationAutocomplete";
import type { LocationSuggestion } from "../lib/location-autocomplete";
import { DateRangeFields, type LeagueGroup } from "./components/SearchBar";
import NearbyFixtureCarousel from "./components/NearbyFixtureCarousel";
import DiscoverShortlist from "./components/DiscoverShortlist";
import AccountConversionPrompt from "./components/AccountConversionPrompt";
import type { Fixture } from "./types/fixture";
import type { InterestedFixture } from "./types/interested";
import { expireDiscoverIfInactive, discoverExpiredEvent, discoverCacheRevision, readDiscoverState, writeDiscoverState, DISCOVER_FRESH_MS, type AppliedSearch, type DiscoverState } from "../lib/discover-state";
import type { MapSearchArea } from "./components/FixtureMap";
import {
  bufferedApiDateBound,
  applyUserLocationEvent,
  beginGeolocationTransition,
  buildViewportDiscoveryParams,
  discoveryDateRangeError,
  endDateAtOrAfterStart,
  isCurrentDiscoveryRequest,
  geolocationErrorMessage,
  GEOLOCATION_INSECURE_MESSAGE,
  GEOLOCATION_UNSUPPORTED_MESSAGE,
  localCalendarDateValue,
  manualCurrentLocationOrigin,
  nextFourteenDaysDateRange,
  normalizeDiscoveryStartDate,
  resolvedLocationTransition,
  selectDiscoveryFixtures,
  orderFixturesByProximity,
  upcomingWeekendDateRange,
} from "../lib/fixtureDiscovery";

const FixtureMap = dynamic(
  () => import("./components/FixtureMap"),
  { ssr: false }
);

type Venue = {
  venue_id: number;
  name: string;
  city: string | null;
  latitude: number | null;
  longitude: number | null;
};

type GeocodingResult = {
  lat: string;
  lon: string;
  display_name: string;
};

type DiscoveryRequestContext = {
  requestVersion: number;
  controller: AbortController;
  origin: { latitude: number; longitude: number };
  locationName: string;
  radius: number;
  startDate: string;
  endDate: string;
  leagueIds: number[];
  showAllStadiums: boolean;
  source: "location" | "map";
  restoring?: boolean;
};

export default function Home() {
  const { accountKey } = useAuth();
  const [reset, setReset] = useState(0);
  useEffect(() => { const expired = () => setReset(value => value + 1); window.addEventListener(discoverExpiredEvent, expired); return () => window.removeEventListener(discoverExpiredEvent, expired); }, []);
  return <DiscoverContent key={`${accountKey}:${reset}`} />;
}

function DiscoverContent() {
  // -------------------------
  // State
  // -------------------------

  const [fixtures, setFixtures] =
    useState<Fixture[]>([]);

  const [leagues, setLeagues] =
    useState<LeagueGroup[]>([]);

  const [visitedVenueIds, setVisitedVenueIds] =
    useState<number[]>([]);

  const [interestedFixtureIds, setInterestedFixtureIds] =
    useState<number[]>([]);

  const [interestedFixtures, setInterestedFixtures] =
    useState<InterestedFixture[]>([]);

  const [updatingInterestedFixtureIds, setUpdatingInterestedFixtureIds] =
    useState<number[]>([]);

  const [venues, setVenues] =
  useState<Venue[]>([]);

  const [loading, setLoading] =
    useState(false);

  const [sessionReady, setSessionReady] =
    useState(false);

  const [isAnonymous, setIsAnonymous] = useState(true);
  const [showAccountPrompt, setShowAccountPrompt] = useState(false);

  const [selectedLeagueIds, setSelectedLeagueIds] =
    useState<number[]>([]);

  const [radius, setRadius] =
    useState(25);

  const [showAllStadiums, setShowAllStadiums] =
    useState(false);

  const [appliedSearch, setAppliedSearch] =
    useState<AppliedSearch | null>(null);

  const [restored, setRestored] = useState(false);
  const [mapPosition, setMapPosition] = useState<DiscoverState["mapPosition"]>(null);
  const [restorePosition, setRestorePosition] = useState<DiscoverState["mapPosition"]>(null);
  const searchArea = useRef<MapSearchArea | null>(null);
  const [restoreArea, setRestoreArea] = useState<MapSearchArea | null>(null);
  const resultsAt = useRef(0);
  const stateToKeep = useRef<DiscoverState | null>(null);
  const cacheRevision = useRef(discoverCacheRevision());
  const [whatsOnExpanded, setWhatsOnExpanded] = useState(false);
  const [shortlistExpanded, setShortlistExpanded] = useState(false);
  const leavingDiscover = useRef(false);
  const [editingSearch, setEditingSearch] =
    useState(true);
  const [selectedFixtureId, setSelectedFixtureId] = useState<number | null>(null);
  const [mapViewportTarget, setMapViewportTarget] = useState({ latitude: 0, longitude: 0, revision: 0 });

  const [discoveryNow, setDiscoveryNow] =
    useState<Date | null>(null);

  const today = discoveryNow ? localCalendarDateValue(discoveryNow) : "";

  const [selectedStartDate, setSelectedStartDate] =
    useState("");

  const startDate = today
    ? normalizeDiscoveryStartDate(selectedStartDate, today)
    : "";

  const [selectedEndDate, setEndDate] =
    useState("");

  const endDate = endDateAtOrAfterStart(startDate, selectedEndDate);

  const [dateError, setDateError] = useState("");
  const [discoveryError, setDiscoveryError] = useState("");
  const [hasCompletedDiscovery, setHasCompletedDiscovery] = useState(false);
  const discoveryRequest = useRef<{
    version: number;
    controller: AbortController;
  } | null>(null);
  const discoveryRequestVersion = useRef(0);
  const pendingResolvedSearch = useRef<DiscoveryRequestContext | null>(null);

  // -------------------------
  // Discovery location
  // -------------------------

  const [locationQuery, setLocationQuery] =
    useState("");

  const [draftCoordinates, setDraftCoordinates] =
    useState<{ latitude: number; longitude: number } | null>(null);

  const [locationLoading, setLocationLoading] =
    useState(false);

  const [locationError, setLocationError] =
    useState("");

  const [manualLocationSelected, setManualLocationSelected] = useState(false);

  const [userLocation, setUserLocation] =
    useState<{ latitude: number; longitude: number } | null>(null);

  // -------------------------
  // Load visited stadiums
  // -------------------------

const loadVisitedStadiums = () => {
  api
    .get("/my-grounds")
    .then((response) => {
      const grounds = response.data as {
        venue_id: number | string;
      }[];

      const venueIds = grounds.map(
        (ground) => Number(ground.venue_id)
      );

      setVisitedVenueIds(venueIds);
    })
    .catch((error) => {
      console.error(
        "Visited stadiums loading error:",
        error
      );
    })
};

  const loadInterestedFixtures = () => {
    api
      .get("/interested")
      .then((response) => {
        const interested = response.data as InterestedFixture[];
        setInterestedFixtures(interested);
        setInterestedFixtureIds(
          interested.map((fixture) => fixture.fixture_id)
        );
      })
      .catch((error) => {
        console.error("Interested loading error:", error);
      });
  };

  const [saveError, setSaveError] = useState("");

  const pendingSaves = useRef(new Set<number>());
  const saveOwnerActive = useRef(true);
  useEffect(() => { saveOwnerActive.current = true; return () => { saveOwnerActive.current = false; }; }, []);
  const toggleInterested = async (fixtureId: number) => {
    if (!sessionReady || pendingSaves.current.has(fixtureId)) return;
    pendingSaves.current.add(fixtureId);
    setSaveError(""); setShowAccountPrompt(false);
    const isInterested = interestedFixtureIds.includes(fixtureId);
    setUpdatingInterestedFixtureIds(current => [...current, fixtureId]);
    try {
      const response = isInterested
        ? await api.delete(`/fixtures/${fixtureId}/interested`)
        : await api.post(`/fixtures/${fixtureId}/interested`);
      if (!saveOwnerActive.current) return;
      if (response.data?.error) throw new Error("Save failed");
      const latest = await api.get<InterestedFixture[]>("/interested");
      if (!saveOwnerActive.current) return;
      if (!Array.isArray(latest.data) || latest.data.some(row => row.fixture_id === fixtureId) === isInterested) {
        throw new Error("Saved state not confirmed");
      }
      setInterestedFixtures(latest.data);
      setInterestedFixtureIds(latest.data.map(row => row.fixture_id));
      if (!isInterested) {
        trackEvent("fixture_saved", { surface: "discover" });
        if (isAnonymous) setShowAccountPrompt(true);
      }
    } catch {
      if (!saveOwnerActive.current) return;
      setSaveError("We couldn't confirm your saved matchdays. Try again to check before making another change.");
    } finally {
      pendingSaves.current.delete(fixtureId);
      setUpdatingInterestedFixtureIds(current => current.filter(id => id !== fixtureId));
    }
  };

  const loadViewportDiscovery = useCallback(async (area: MapSearchArea, context: DiscoveryRequestContext) => {
    const {
      requestVersion,
      controller,
      origin,
      locationName,
      radius: requestRadius,
      startDate: requestStartDate,
      endDate: requestEndDate,
      leagueIds,
      showAllStadiums: requestShowAllStadiums,
      source,
    } = context;

    try {
      const response = await api.get("/nearby", {
        signal: controller.signal,
        params: buildViewportDiscoveryParams(area, {
          startDate: requestStartDate ? bufferedApiDateBound(requestStartDate, -1) : undefined,
          endDate: requestEndDate ? bufferedApiDateBound(requestEndDate, 1) : undefined,
          leagueIds,
        }),
        paramsSerializer: { indexes: null },
      });
      if (!isCurrentDiscoveryRequest(discoveryRequestVersion.current, requestVersion)) return;

      const nextSearch: AppliedSearch = {
        latitude: area.center.latitude,
        longitude: area.center.longitude,
        locationName: source === "location" ? locationName : "Map area",
        radius: requestRadius,
        startDate: requestStartDate,
        endDate: requestEndDate,
        leagueIds: [...leagueIds],
        showAllStadiums: requestShowAllStadiums,
        mode: source === "location" ? "radius" : "viewport",
        totalMatches: Number(response.headers["x-total-matches"] ?? response.data.length),
        resultsLimited: response.headers["x-results-limited"] === "true",
      };
      searchArea.current = area;
      resultsAt.current = Date.now();
      setFixtures(response.data);
      if (!context.restoring) trackEvent("location_search", { search_method: source, result_count_bucket: resultBucket(Number(response.headers["x-total-matches"] ?? response.data.length)) });
      if (!context.restoring) { setSelectedFixtureId(null); setWhatsOnExpanded(false); setShortlistExpanded(false); }
      setAppliedSearch(nextSearch);
      setLocationQuery(nextSearch.locationName);
      if (source === "map") setManualLocationSelected(false);
      setDraftCoordinates(source === "location" ? origin : area.center);
      setRadius(nextSearch.radius);
      setSelectedStartDate(nextSearch.startDate);
      setEndDate(nextSearch.endDate);
      setSelectedLeagueIds([...nextSearch.leagueIds]);
      setShowAllStadiums(nextSearch.showAllStadiums);
      setHasCompletedDiscovery(true);
      setEditingSearch(false);

      if (requestShowAllStadiums) {
        const venueResponse = await api.get("/venues", {
          signal: controller.signal,
          params: {
            north: area.north,
            south: area.south,
            east: area.east,
            west: area.west,
            limit: 250,
          },
        });
        if (isCurrentDiscoveryRequest(discoveryRequestVersion.current, requestVersion)) setVenues(venueResponse.data);
      } else {
        setVenues([]);
      }
    } catch (error) {
      if (controller.signal.aborted || axios.isCancel(error) || !isCurrentDiscoveryRequest(discoveryRequestVersion.current, requestVersion)) return;
      resultsAt.current = 0;
      console.error(source === "location" ? "Location discovery error:" : "Map-area discovery error:", error);
      setFixtures([]);
      setHasCompletedDiscovery(false);
      setDiscoveryError(apiErrorMessage(error, source === "location"
        ? "Unable to load fixtures for that location. Please try again."
        : "Unable to search this map area. Please try again."));
    } finally {
      if (isCurrentDiscoveryRequest(discoveryRequestVersion.current, requestVersion)) {
        setLoading(false);
        setLocationLoading(false);
        discoveryRequest.current = null;
      }
    }
  }, [setEndDate, setSelectedStartDate]);

  const handleResolvedViewport = useCallback((area: MapSearchArea) => {
    const pending = pendingResolvedSearch.current;
    if (!pending || !isCurrentDiscoveryRequest(discoveryRequestVersion.current, pending.requestVersion)) return;
    pendingResolvedSearch.current = null;
    void loadViewportDiscovery(area, pending);
  }, [loadViewportDiscovery]);

  const stageResolvedLocation = useCallback((context: DiscoveryRequestContext) => {
    const { origin, locationName, requestVersion } = context;
    pendingResolvedSearch.current = context;
    setFixtures([]);
    setVenues([]);
    setLoading(true);
    setHasCompletedDiscovery(false);
    setDiscoveryError("");
    setAppliedSearch({
      ...origin,
      locationName,
      radius: context.radius,
      startDate: context.startDate,
      endDate: context.endDate,
      leagueIds: [...context.leagueIds],
      showAllStadiums: context.showAllStadiums,
      mode: "viewport",
      totalMatches: 0,
      resultsLimited: false,
    });
    setLocationQuery(locationName);
    setDraftCoordinates(origin);
    setMapViewportTarget((current) =>
      resolvedLocationTransition(origin, locationName, requestVersion, current.revision).viewportTarget
    );
    setEditingSearch(false);
  }, []);

  const submitDiscovery = async (event?: FormEvent<HTMLFormElement>, selected?: LocationSuggestion) => {
    event?.preventDefault();
    if (loading) return;

    const requestVersion = discoveryRequestVersion.current + 1;
    discoveryRequestVersion.current = requestVersion;
    discoveryRequest.current?.controller.abort();
    pendingResolvedSearch.current = null;

    const rangeError = discoveryDateRangeError(startDate, endDate);
    if (rangeError) {
      setDateError(rangeError);
      setDiscoveryError("");
      setFixtures([]);
      setLoading(false);
      setHasCompletedDiscovery(false);
      return;
    }

    const query = selected?.label ?? locationQuery.trim();
    if (!query) {
      setLocationError("Enter a city or location to search.");
      return;
    }

    const controller = new AbortController();
    discoveryRequest.current = { version: requestVersion, controller };
    setFixtures([]);
    setVenues([]);
    setLoading(true);
    setHasCompletedDiscovery(false);
    setDateError("");
    setDiscoveryError("");
    setLocationError("");
    let resolvingLocation = !selected && !draftCoordinates;
    let awaitingViewport = false;

    try {
      let origin = selected ? { latitude: selected.latitude, longitude: selected.longitude } : draftCoordinates;
      let locationName = query;

      if (!origin) {
        const searchParams = new URLSearchParams({ q: query, format: "jsonv2", limit: "1" });
        const locationResponse = await fetch(
          `https://nominatim.openstreetmap.org/search?${searchParams.toString()}`,
          { headers: { Accept: "application/json" }, signal: controller.signal }
        );
        if (!locationResponse.ok) throw new Error("Location search failed");
        const results = await locationResponse.json() as GeocodingResult[];
        if (!results[0]) {
          setLocationError("No matching location was found. Try a more specific search.");
          return;
        }
        origin = { latitude: Number(results[0].lat), longitude: Number(results[0].lon) };
        locationName = results[0].display_name;
        resolvingLocation = false;
      }

      if (!isCurrentDiscoveryRequest(discoveryRequestVersion.current, requestVersion)) return;
      const context: DiscoveryRequestContext = {
        requestVersion,
        controller,
        origin,
        locationName,
        radius,
        startDate,
        endDate,
        leagueIds: [...selectedLeagueIds],
        showAllStadiums,
        source: "location",
      };
      awaitingViewport = true;
      stageResolvedLocation(context);
    } catch (error) {
      if (controller.signal.aborted || axios.isCancel(error) || discoveryRequestVersion.current !== requestVersion) return;
      console.error("Discovery loading error:", error);
      setFixtures([]);
      setHasCompletedDiscovery(false);
      if (resolvingLocation) {
        setLocationError("Unable to search for that location. Please try again.");
      } else {
        setDiscoveryError(apiErrorMessage(error, "Unable to load nearby fixtures. Please try again."));
      }
    } finally {
      if (!awaitingViewport && isCurrentDiscoveryRequest(discoveryRequestVersion.current, requestVersion)) {
        setLoading(false);
        setLocationLoading(false);
        discoveryRequest.current = null;
      }
    }
  };

  const searchMapArea = async (area: MapSearchArea) => {
    if (loading || !appliedSearch) return;
    const requestVersion = discoveryRequestVersion.current + 1;
    discoveryRequestVersion.current = requestVersion;
    discoveryRequest.current?.controller.abort();
    pendingResolvedSearch.current = null;
    const controller = new AbortController();
    discoveryRequest.current = { version: requestVersion, controller };
    setLoading(true);
    setDiscoveryError("");

    await loadViewportDiscovery(area, {
      requestVersion,
      controller,
      origin: area.center,
      locationName: "Map area",
      radius: appliedSearch.radius,
      startDate: appliedSearch.startDate,
      endDate: appliedSearch.endDate,
      leagueIds: [...appliedSearch.leagueIds],
      showAllStadiums: appliedSearch.showAllStadiums,
      source: "map",
    });
  };

  useEffect(() => () => {
    discoveryRequest.current?.controller.abort();
    pendingResolvedSearch.current = null;
  }, []);

  // Public discovery state survives route/account remounts; identity state never does.
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
    leavingDiscover.current = false;
    const saved = readDiscoverState();
    cacheRevision.current = discoverCacheRevision();
    if (saved) {
      setAppliedSearch(saved.appliedSearch); setFixtures(saved.fixtures); setVenues(saved.venues);
      setLocationQuery(saved.locationQuery); setDraftCoordinates(saved.draftCoordinates);
      setRadius(saved.radius); setSelectedStartDate(saved.startDate); setEndDate(saved.endDate);
      setSelectedLeagueIds(saved.leagueIds); setShowAllStadiums(saved.showAllStadiums);
      setEditingSearch(saved.editingSearch); setMapPosition(saved.mapPosition); setRestorePosition(saved.mapPosition); setRestoreArea(saved.searchArea);
      setHasCompletedDiscovery(saved.resultsAt > 0);
      setSelectedFixtureId(saved.fixtures.some(row => row.fixture_id === saved.selectedFixtureId) ? saved.selectedFixtureId : null);
      resultsAt.current = saved.resultsAt; searchArea.current = saved.searchArea;
      setWhatsOnExpanded(saved.whatsOnExpanded ?? false); setShortlistExpanded(saved.shortlistExpanded ?? false);
    }
    setRestored(true);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (!restored) return;
    const snapshot: DiscoverState = { appliedSearch, fixtures, venues, locationQuery,
      draftCoordinates, radius, startDate: selectedStartDate, endDate: selectedEndDate,
      leagueIds: selectedLeagueIds, showAllStadiums, editingSearch, mapPosition,
      selectedFixtureId, searchArea: searchArea.current, resultsAt: resultsAt.current,
      scrollY: 0, whatsOnExpanded, shortlistExpanded };
    stateToKeep.current = snapshot;
    // Never replace the last completed search with a half-resolved request.
    if (!loading && !locationLoading && !leavingDiscover.current) writeDiscoverState(snapshot, undefined, cacheRevision.current);
  }, [restored, appliedSearch, fixtures, venues, locationQuery, draftCoordinates, radius,
    selectedStartDate, selectedEndDate, selectedLeagueIds, showAllStadiums, editingSearch,
    mapPosition, selectedFixtureId, loading, locationLoading, whatsOnExpanded, shortlistExpanded]);

  useEffect(() => {
    const capture = () => {
      if (stateToKeep.current && !discoveryRequest.current && !leavingDiscover.current) {
        stateToKeep.current.scrollY = 0;
        writeDiscoverState(stateToKeep.current, undefined, cacheRevision.current);
      }
    };
    // Capture before the router resets scroll, and ignore that reset as user input.
    const leaving = () => { capture(); leavingDiscover.current = true; };
    const navigationClick = (event: MouseEvent) => {
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.getAttribute("target") === "_blank") return;
      const destination = new URL(link.getAttribute("href")!, window.location.href);
      if (destination.origin === window.location.origin && destination.pathname !== "/") leaving();
    };
    const backNavigation = () => { if (window.location.pathname !== "/") leaving(); };
    document.addEventListener("click", navigationClick, true);
    window.addEventListener("popstate", backNavigation);
    window.addEventListener("pagehide", capture);
    return () => { window.removeEventListener("pagehide", capture); document.removeEventListener("click", navigationClick, true); window.removeEventListener("popstate", backNavigation); if (stateToKeep.current && !discoveryRequest.current) writeDiscoverState(stateToKeep.current, undefined, cacheRevision.current); };
  }, []);

  useEffect(() => {
    if (!restored || !appliedSearch) return;
    let lastAttempt = 0;
    const refresh = () => {
      if (expireDiscoverIfInactive() || cacheRevision.current !== discoverCacheRevision()) return;
      if (document.visibilityState === "hidden" || discoveryRequest.current || !searchArea.current ||
        Date.now() - resultsAt.current < DISCOVER_FRESH_MS || Date.now() - lastAttempt < 60_000) return;
      lastAttempt = Date.now();
      const requestVersion = ++discoveryRequestVersion.current;
      const controller = new AbortController();
      discoveryRequest.current = { version: requestVersion, controller }; setLoading(true);
      void loadViewportDiscovery(searchArea.current, { requestVersion, controller,
        origin: { latitude: appliedSearch.latitude, longitude: appliedSearch.longitude },
        locationName: appliedSearch.locationName, radius: appliedSearch.radius,
        startDate: appliedSearch.startDate, endDate: appliedSearch.endDate,
        leagueIds: appliedSearch.leagueIds, showAllStadiums: appliedSearch.showAllStadiums,
        source: appliedSearch.mode === "radius" ? "location" : "map", restoring: true });
    };
    refresh(); const timer = window.setInterval(refresh, 60_000);
    window.addEventListener("focus", refresh); document.addEventListener("visibilitychange", refresh);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, [restored, appliedSearch, loadViewportDiscovery]);

  // -------------------------
  // Establish anonymous session
  // -------------------------

  useEffect(() => {
    api
      .get("/session")
      .then((response) => {
        console.log(
          "Anonymous session:",
          response.data
        );

        setSessionReady(true);
        setIsAnonymous(response.data.anonymous !== false);
      })
      .catch((error) => {
        console.error(
          "Session error:",
          error
        );
      });
  }, []);

  // -------------------------
  // Load leagues once
  // -------------------------

  useEffect(() => {
    api
      .get("/leagues")
      .then((response) => {
        setLeagues(response.data);
      })
      .catch((error) => {
        console.error(
          "League loading error:",
          error
        );
      });
  }, []);

  // -------------------------
  // Load user-specific data
  // session is ready
  // -------------------------

  useEffect(() => {
    if (!sessionReady) {
      return;
    }

    const timeout = window.setTimeout(() => {
      loadVisitedStadiums();
      loadInterestedFixtures();
    }, 0);

    return () => window.clearTimeout(timeout);
  }, [sessionReady]);

  // -------------------------
  // Set discovery location
  // -------------------------

  const resolveCurrentLocation = (searchOptions?: {
    radius: number;
    startDate: string;
    endDate: string;
    leagueIds: number[];
    showAllStadiums: boolean;
  }, establishOriginOnly = false) => {
    const transition = beginGeolocationTransition(discoveryRequestVersion.current);
    const requestVersion = transition.requestVersion;
    discoveryRequestVersion.current = requestVersion;
    discoveryRequest.current?.controller.abort();
    discoveryRequest.current = null;
    pendingResolvedSearch.current = null;
    setDraftCoordinates(transition.draftCoordinates);
    setMapViewportTarget(transition.viewportTarget);

    if (!window.isSecureContext) {
      setLocationError(GEOLOCATION_INSECURE_MESSAGE);
      setLocationLoading(false);
      return;
    }
    if (!navigator.geolocation) {
      setLocationError(GEOLOCATION_UNSUPPORTED_MESSAGE);
      return;
    }

    const controller = new AbortController();
    discoveryRequest.current = { version: requestVersion, controller };
    setLocationLoading(true);
    setLocationError("");
    setDiscoveryError("");

    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (!isCurrentDiscoveryRequest(discoveryRequestVersion.current, requestVersion)) return;
        const origin = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        };
        if (establishOriginOnly) {
          const manualOrigin = manualCurrentLocationOrigin(origin);
          setDraftCoordinates(manualOrigin.draftCoordinates);
          setLocationQuery(manualOrigin.locationQuery);
          setUserLocation(manualOrigin.userLocation);
          setManualLocationSelected(true);
          setLocationLoading(false);
          discoveryRequest.current = null;
          return;
        }
        setUserLocation((current) => applyUserLocationEvent(current, { type: "geolocation", location: origin }));
        const options = searchOptions ?? { radius, startDate, endDate, leagueIds: [...selectedLeagueIds], showAllStadiums };
        stageResolvedLocation({
          requestVersion,
          controller,
          origin,
          locationName: "Current location",
          ...options,
          source: "location",
        });
      },
      (positionError) => {
        if (!isCurrentDiscoveryRequest(discoveryRequestVersion.current, requestVersion)) return;
        setLocationError(geolocationErrorMessage(positionError.code));
        if (establishOriginOnly) setManualLocationSelected(false);
        setLocationLoading(false);
        setLoading(false);
        discoveryRequest.current = null;
      },
      { timeout: 10_000, maximumAge: 60_000 }
    );
  };

  const findFootballThisWeekend = () => {
    const weekend = upcomingWeekendDateRange(new Date());
    setSelectedStartDate(weekend.startDate);
    setEndDate(weekend.endDate);
    setRadius(25);
    setSelectedLeagueIds([]);
    setShowAllStadiums(false);
    setManualLocationSelected(false);
    resolveCurrentLocation({ ...weekend, radius: 25, leagueIds: [], showAllStadiums: false });
  };

  useEffect(() => {
    const initializeClock = window.requestAnimationFrame(() => {
      const localNow = new Date();
      const initialRange = nextFourteenDaysDateRange(localNow);
      setDiscoveryNow(localNow);
      setSelectedStartDate((current) => current || initialRange.startDate);
      setEndDate((current) => current || initialRange.endDate);
    });

    const clock = window.setInterval(
      () => setDiscoveryNow(new Date()),
      60_000
    );

    return () => {
      window.cancelAnimationFrame(initializeClock);
      window.clearInterval(clock);
    };
  }, []);

  // -------------------------
  // UI
  // -------------------------

  const visibleFixtures = useMemo(
    () => discoveryNow ? selectDiscoveryFixtures(
      fixtures,
      appliedSearch?.radius ?? radius,
      discoveryNow,
      appliedSearch?.startDate ?? startDate,
      appliedSearch?.endDate ?? endDate,
      appliedSearch?.mode !== "viewport",
    ) : [],
    [appliedSearch, discoveryNow, endDate, fixtures, radius, startDate]
  );

  const proximityFixtures = useMemo(() => orderFixturesByProximity(visibleFixtures, appliedSearch), [visibleFixtures, appliedSearch]);

  const shortlistFixtures = useMemo(() => discoveryNow ? interestedFixtures
    .filter((fixture) => !fixture.kickoff_passed && new Date(fixture.fixture_date).getTime() > discoveryNow.getTime())
    .sort((left, right) => new Date(left.fixture_date).getTime() - new Date(right.fixture_date).getTime()) : [], [discoveryNow, interestedFixtures]);

  const formatSummaryDate = (value: string) => value
    ? new Date(`${value}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" })
    : "Any date";

  const appliedDateSummary = appliedSearch
    ? appliedSearch.startDate === appliedSearch.endDate
      ? formatSummaryDate(appliedSearch.startDate)
      : `${formatSummaryDate(appliedSearch.startDate)}–${formatSummaryDate(appliedSearch.endDate)}`
    : "";
  const defaultDateRange = discoveryNow
    ? nextFourteenDaysDateRange(discoveryNow)
    : { startDate: "", endDate: "" };
  const usingDefaultDateRange = startDate === defaultDateRange.startDate && endDate === defaultDateRange.endDate;

  return (
    <main className="mx-auto w-full min-w-0 max-w-7xl px-4 py-4 sm:px-6 sm:py-8 lg:px-8">
      <AccountConversionPrompt open={showAccountPrompt} kind="interested" onDismiss={() => setShowAccountPrompt(false)} />

      <header className="mb-3 border-b-2 border-[var(--tt-ink)] pb-3 sm:mb-5 sm:pb-4">
        <p className="mg-section-label">01 / Match discovery</p>
        <h1 className="mg-display-page mt-1 max-w-4xl !text-4xl sm:!text-6xl">Find your next matchday.</h1>
        <p className="mg-body mt-2 max-w-xl !text-sm text-[var(--tt-muted)]">
          Discover football worth going to, wherever you are.
        </p>
      </header>

      <section className={editingSearch || !appliedSearch ? "mb-4 w-full min-w-0 sm:mb-6" : "mg-utility-panel mb-5 w-full min-w-0 px-3 py-1 sm:px-4"} aria-labelledby="search-heading">
        {!editingSearch && appliedSearch ? (
          <div className="flex items-center justify-between gap-3">
            <p className="min-w-0 break-words py-2 text-sm font-extrabold" id="search-heading">
              {appliedSearch.locationName.split(",")[0]} · {appliedDateSummary} · {appliedSearch.leagueIds.length === 0 ? "All competitions" : `${appliedSearch.leagueIds.length} ${appliedSearch.leagueIds.length === 1 ? "competition" : "competitions"}`}
            </p>
            <button type="button" onClick={() => setEditingSearch(true)} className="min-h-11 shrink-0 px-2 text-xs font-extrabold uppercase tracking-[0.1em] text-[var(--brand-interactive)] underline decoration-2 underline-offset-4">Change search</button>
          </div>
        ) : (
          <form onSubmit={submitDiscovery} className="max-w-5xl">
            <h2 className="sr-only" id="search-heading">Search for football</h2>
            <button type="button" onClick={findFootballThisWeekend} disabled={!discoveryNow || loading || locationLoading} className="mg-primary-action w-full px-4 text-sm disabled:cursor-not-allowed disabled:opacity-60 sm:min-h-14 sm:max-w-xl">
              {locationLoading ? "Finding your location…" : "Find football near me this weekend"}
            </button>
            <div className="my-2 flex max-w-xl items-center gap-3 text-[0.65rem] font-extrabold uppercase tracking-[0.12em] text-[var(--tt-muted)]" aria-hidden="true">
              <span className="h-px flex-1 bg-[var(--tt-rule)]" />or<span className="h-px flex-1 bg-[var(--tt-rule)]" />
            </div>
            <div className="grid gap-2 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] lg:gap-8">
            <div className="grid content-start gap-1 text-xs font-extrabold uppercase tracking-[0.12em]">
              Where?
              <div>
                <LocationAutocomplete
                  value={locationQuery}
                  disabled={loading || locationLoading}
                  onChange={(value) => {
                    setLocationQuery(value);
                    setDraftCoordinates(null);
                    setManualLocationSelected(false);
                    setUserLocation((current) => applyUserLocationEvent(current, { type: "manual-location" }));
                  }}
                  onSelect={(location) => {
                    setLocationQuery(location.label);
                    setDraftCoordinates({ latitude: location.latitude, longitude: location.longitude });
                    void submitDiscovery(undefined, location);
                  }}
                />
                <button type="button" onClick={() => resolveCurrentLocation(undefined, true)} disabled={locationLoading || loading} className="mt-1 min-h-11 px-1 text-left text-xs font-extrabold normal-case tracking-normal text-[var(--brand-interactive)] underline decoration-2 underline-offset-4 disabled:opacity-60">
                  {locationLoading ? "Finding your location…" : manualLocationSelected ? "Using your location ✓" : "Use my location"}
                </button>
              </div>
            </div>

            <div className="pt-1.5 lg:pt-0">
              <p className="mb-1 text-xs font-extrabold uppercase tracking-[0.12em]">When? <span className="ml-1 font-bold normal-case tracking-normal text-[var(--tt-muted)]">{usingDefaultDateRange ? "Next 14 days" : "Custom dates"}</span></p>
              <div className={discoveryNow ? "" : "invisible"} aria-hidden={discoveryNow ? undefined : true}>
                <DateRangeFields startDate={startDate} setStartDate={setSelectedStartDate} minimumStartDate={today} endDate={endDate} setEndDate={setEndDate} />
              </div>
            </div>
            </div>

            <details className="mt-2 max-w-5xl border-t border-[var(--tt-rule)] pt-1">
              <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between text-xs font-extrabold uppercase tracking-[0.12em] marker:content-none">
                <span>Filters</span><span aria-hidden="true">＋</span>
              </summary>
              <div className="pb-1 pt-2">
                <SearchBar leagues={leagues} selectedLeagueIds={selectedLeagueIds} setSelectedLeagueIds={setSelectedLeagueIds} radius={radius} setRadius={setRadius} />
                <label className="mt-3 flex min-h-11 cursor-pointer items-center gap-2 border-t border-[var(--tt-rule)] pt-3 text-xs font-bold text-[var(--tt-muted)]">
                  <input type="checkbox" checked={showAllStadiums} onChange={(event) => setShowAllStadiums(event.target.checked)} className="h-4 w-4 accent-[var(--brand-interactive)]" />
                  <span>Show stadiums without fixtures</span>
                </label>
              </div>
            </details>

            <button type="submit" disabled={!discoveryNow || loading || locationLoading} className="mg-primary-action mt-3 w-full px-5 disabled:cursor-not-allowed disabled:opacity-60 sm:block sm:w-auto sm:min-w-40">{loading ? "Searching…" : "Search"}</button>

            {locationError && <p role="alert" className="mt-3 border-l-4 border-[var(--brand-interactive)] bg-[var(--tt-newsprint)] p-3 text-sm font-semibold normal-case tracking-normal">{locationError}</p>}
            {dateError && <p role="alert" className="mt-3 border-l-4 border-[var(--brand-interactive)] bg-[var(--tt-newsprint)] p-3 text-sm font-semibold normal-case tracking-normal">{dateError}</p>}
          </form>
        )}
      </section>


      {/* Map */}

      {appliedSearch && (
          <section className="mb-7 w-full min-w-0 max-w-full overflow-x-clip" aria-label={`Matches near ${appliedSearch.locationName.split(",")[0]}`}>
            <div className="mb-3">
              <p className="mg-section-label">02 / See the area</p>
              <h2 className="mg-display-section mt-1">Football around you</h2>
            </div>
            <div className="border-y-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] py-1">
<FixtureMap
  interestedFixtureIds={interestedFixtureIds}
  updatingFixtureIds={updatingInterestedFixtureIds}
  onToggleInterested={toggleInterested}
  fixtures={visibleFixtures}
  venues={venues}
  latitude={appliedSearch.latitude}
  longitude={appliedSearch.longitude}
  visitedVenueIds={visitedVenueIds}
  showAllStadiums={appliedSearch.showAllStadiums}
  radius={appliedSearch.radius}
  viewportLatitude={mapViewportTarget.revision ? mapViewportTarget.latitude : appliedSearch.latitude}
  viewportLongitude={mapViewportTarget.revision ? mapViewportTarget.longitude : appliedSearch.longitude}
  viewportRevision={mapViewportTarget.revision}
  searchingArea={loading}
  onSearchArea={searchMapArea}
  onViewportReady={handleResolvedViewport}
  initialPosition={restorePosition}
  searchedArea={restoreArea}
  onPositionChange={setMapPosition}
  userLocation={userLocation}
  selectedFixtureId={selectedFixtureId}
  onFixtureSelect={setSelectedFixtureId}
  onFixtureDismiss={(fixtureId) => setSelectedFixtureId((current) => current === fixtureId ? null : current)}
  showDistance={appliedSearch.mode !== "viewport"}
  distanceOrigin={appliedSearch.locationName}
/>
            </div>
            {saveError && <p role="alert" className="mt-3 text-sm font-bold text-[var(--brand-interactive)]">{saveError} <button type="button" onClick={() => { setSaveError(""); void api.get<InterestedFixture[]>("/interested").then(response => { if (!Array.isArray(response.data)) throw new Error("Invalid saved list"); setInterestedFixtures(response.data); setInterestedFixtureIds(response.data.map(row => row.fixture_id)); }).catch(() => setSaveError("Your saved matchdays could not be checked. Please try again.")); }} className="min-h-11 underline">Try again</button></p>}
            <NearbyFixtureCarousel
              fixtures={proximityFixtures}
              expanded={whatsOnExpanded}
              onExpandedChange={setWhatsOnExpanded}
              showDistance={appliedSearch.mode !== "viewport"}
  distanceOrigin={appliedSearch.locationName}
              totalMatches={appliedSearch.resultsLimited ? appliedSearch.totalMatches : visibleFixtures.length}
              resultsLimited={appliedSearch.resultsLimited}
              interestedFixtureIds={interestedFixtureIds}
              updatingFixtureIds={updatingInterestedFixtureIds}
              selectedFixtureId={selectedFixtureId}
              onFixtureSelect={setSelectedFixtureId}
              onToggleInterested={toggleInterested}
            />
          </section>
        )}

      {discoveryError && (
        <p role="alert" className="border-l-4 border-[var(--brand-interactive)] bg-[var(--tt-paper)] p-3 text-sm font-semibold">{discoveryError}</p>
      )}

      {!loading &&
        !dateError &&
        !discoveryError &&
        hasCompletedDiscovery &&
        visibleFixtures.length === 0 && (
          <div className="tt-panel border-l-[8px] border-l-[var(--brand-interactive)] p-5"><p className="font-semibold">No fixtures found.</p><p className="mt-1 text-sm text-[var(--tt-muted)]">Try a wider radius, more competitions, or different dates.</p></div>
        )}

      {loading && (
        <p className="tt-kicker py-4" aria-live="polite">Loading fixtures...</p>
      )}

      <TerracePublicGallery mode="preview" />
      <DiscoverShortlist fixtures={shortlistFixtures} discoveredFixtures={fixtures} expanded={shortlistExpanded} onExpandedChange={setShortlistExpanded} updatingFixtureIds={updatingInterestedFixtureIds} onRemove={toggleInterested} />

    </main>
  );
}
