"use client";

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
import dynamic from "next/dynamic";

import SearchBar from "./components/SearchBar";
import { DateRangeFields, type LeagueGroup } from "./components/SearchBar";
import NearbyFixtureCarousel from "./components/NearbyFixtureCarousel";
import DiscoverShortlist from "./components/DiscoverShortlist";
import AccountConversionPrompt from "./components/AccountConversionPrompt";
import type { Fixture } from "./types/fixture";
import type { InterestedFixture } from "./types/interested";
import type { MapSearchArea } from "./components/FixtureMap";
import {
  bufferedApiDateBound,
  applyUserLocationEvent,
  beginGeolocationTransition,
  buildViewportDiscoveryParams,
  discoveryDateRangeError,
  isCurrentDiscoveryRequest,
  geolocationErrorMessage,
  GEOLOCATION_INSECURE_MESSAGE,
  GEOLOCATION_UNSUPPORTED_MESSAGE,
  localCalendarDateValue,
  manualCurrentLocationOrigin,
  normalizeDiscoveryStartDate,
  resolvedLocationTransition,
  selectDiscoveryFixtures,
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

type AppliedSearch = {
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
};

export default function Home() {
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

  const [editingSearch, setEditingSearch] =
    useState(true);
  const [selectedFixtureId, setSelectedFixtureId] = useState<number | null>(null);
  const [mapViewportTarget, setMapViewportTarget] = useState({ latitude: 0, longitude: 0, revision: 0 });

  const [discoveryNow, setDiscoveryNow] =
    useState(() => new Date());

  const today = localCalendarDateValue(discoveryNow);

  const [selectedStartDate, setSelectedStartDate] =
    useState(() => upcomingWeekendDateRange(discoveryNow).startDate);

  const startDate = normalizeDiscoveryStartDate(
    selectedStartDate,
    today
  );

  const [endDate, setEndDate] =
    useState(() => upcomingWeekendDateRange(discoveryNow).endDate);

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

  const toggleInterested = (fixtureId: number) => {
    if (updatingInterestedFixtureIds.includes(fixtureId)) {
      return;
    }

    const isInterested = interestedFixtureIds.includes(fixtureId);
    setUpdatingInterestedFixtureIds((current) => [...current, fixtureId]);

    const request = isInterested
      ? api.delete(`/fixtures/${fixtureId}/interested`)
      : api.post(`/fixtures/${fixtureId}/interested`);

    request
      .then(() => {
        if (isInterested) {
          setInterestedFixtures((current) => current.filter((fixture) => fixture.fixture_id !== fixtureId));
        } else {
          loadInterestedFixtures();
        }
        setInterestedFixtureIds((current) =>
          isInterested
            ? current.filter((id) => id !== fixtureId)
            : [...current, fixtureId]
        );
        if (!isInterested && isAnonymous) {
          setShowAccountPrompt(true);
        }
      })
      .catch((error) => {
        console.error("Interested update error:", error);
      })
      .finally(() => {
        setUpdatingInterestedFixtureIds((current) =>
          current.filter((id) => id !== fixtureId)
        );
      });
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
      setFixtures(response.data);
      setSelectedFixtureId(null);
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
  }, [setSelectedStartDate]);

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

  const submitDiscovery = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
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

    const query = locationQuery.trim();
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
    let resolvingLocation = !draftCoordinates;
    let awaitingViewport = false;

    try {
      let origin = draftCoordinates;
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
    const clock = window.setInterval(
      () => setDiscoveryNow(new Date()),
      60_000
    );

    return () => window.clearInterval(clock);
  }, []);

  // -------------------------
  // UI
  // -------------------------

  const visibleFixtures = useMemo(
    () => selectDiscoveryFixtures(
      fixtures,
      appliedSearch?.radius ?? radius,
      discoveryNow,
      appliedSearch?.startDate ?? startDate,
      appliedSearch?.endDate ?? endDate,
      appliedSearch?.mode !== "viewport",
    ),
    [appliedSearch, discoveryNow, endDate, fixtures, radius, startDate]
  );

  const shortlistFixtures = useMemo(() => interestedFixtures
    .filter((fixture) => !fixture.kickoff_passed && new Date(fixture.fixture_date).getTime() > discoveryNow.getTime())
    .sort((left, right) => new Date(left.fixture_date).getTime() - new Date(right.fixture_date).getTime()), [discoveryNow, interestedFixtures]);

  const formatSummaryDate = (value: string) => value
    ? new Date(`${value}T12:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" })
    : "Any date";

  const appliedDateSummary = appliedSearch
    ? appliedSearch.startDate === appliedSearch.endDate
      ? formatSummaryDate(appliedSearch.startDate)
      : `${formatSummaryDate(appliedSearch.startDate)}–${formatSummaryDate(appliedSearch.endDate)}`
    : "";

  return (
    <main className="mx-auto w-full min-w-0 max-w-6xl px-4 py-2 sm:px-6 sm:py-8">
      <AccountConversionPrompt open={showAccountPrompt} kind="interested" onDismiss={() => setShowAccountPrompt(false)} />

      <header className="mb-2 border-b-2 border-[var(--tt-ink)] pb-2 sm:mb-6 sm:pb-5">
        <p className="tt-kicker">01 / Match discovery</p>
        <h1 className="tt-display mt-0.5 text-3xl leading-[0.9] sm:mt-2 sm:text-6xl">Find your next matchday</h1>
        <p className="mt-1 max-w-xl text-xs text-[var(--tt-muted)] sm:mt-2 sm:text-base">
          Find nearby football, compare the choices and understand the matchday before you go.
        </p>
      </header>

      <section className={editingSearch || !appliedSearch ? "tt-panel mb-4 w-full min-w-0 p-2.5 sm:p-4" : "mb-2 w-full min-w-0 border-y border-[var(--tt-rule)] py-2"} aria-labelledby="search-heading">
        {!editingSearch && appliedSearch ? (
          <div className="flex items-center justify-between gap-3">
            <p className="min-w-0 truncate text-sm font-extrabold" id="search-heading">
              {appliedSearch.locationName.split(",")[0]} · {appliedDateSummary} · {appliedSearch.leagueIds.length === 0 ? "All leagues" : `${appliedSearch.leagueIds.length} ${appliedSearch.leagueIds.length === 1 ? "league" : "leagues"}`}
            </p>
            <button type="button" onClick={() => setEditingSearch(true)} className="min-h-11 shrink-0 px-2 text-xs font-extrabold uppercase tracking-[0.1em] text-[var(--tt-blue)] underline decoration-2 underline-offset-4">Edit</button>
          </div>
        ) : (
          <form onSubmit={submitDiscovery}>
            <p className="tt-kicker mb-2" id="search-heading">Start here</p>
            <button type="button" onClick={findFootballThisWeekend} disabled={loading || locationLoading} className="tt-action w-full px-4 text-sm disabled:cursor-not-allowed disabled:opacity-60 sm:min-h-14">
              {locationLoading ? "Finding your location…" : "Find football near me this weekend"}
            </button>
            <div className="my-3 flex items-center gap-3 text-[0.65rem] font-extrabold uppercase tracking-[0.12em] text-[var(--tt-muted)]" aria-hidden="true">
              <span className="h-px flex-1 bg-[var(--tt-rule)]" />or search a place<span className="h-px flex-1 bg-[var(--tt-rule)]" />
            </div>
            <div className="grid gap-1 text-xs font-extrabold uppercase tracking-[0.12em]">
              Where do you want to go?
              <div>
                <input
                  id="location-search"
                  type="search"
                  value={locationQuery}
                  onChange={(event) => {
                    setLocationQuery(event.target.value);
                    setDraftCoordinates(null);
                    setManualLocationSelected(false);
                    setUserLocation((current) => applyUserLocationEvent(current, { type: "manual-location" }));
                  }}
                  placeholder="Search a city or location"
                  aria-label="Where"
                  className="tt-control w-full min-w-0 px-4 py-2 normal-case tracking-normal"
                />
                <button type="button" onClick={() => resolveCurrentLocation(undefined, true)} disabled={locationLoading || loading} className="mt-1 min-h-11 px-1 text-left text-xs font-extrabold normal-case tracking-normal text-[var(--tt-blue)] underline decoration-2 underline-offset-4 disabled:opacity-60">
                  {locationLoading ? "Finding your location…" : manualLocationSelected ? "Using your location ✓" : "Use my location"}
                </button>
              </div>
            </div>

            <div className="mt-2 border-t border-[var(--tt-rule)] pt-2">
              <p className="mb-2 text-xs font-extrabold uppercase tracking-[0.12em]">When?</p>
              <DateRangeFields startDate={startDate} setStartDate={setSelectedStartDate} minimumStartDate={today} endDate={endDate} setEndDate={setEndDate} />
            </div>

            <details className="mt-3 border-t border-[var(--tt-rule)] pt-3">
              <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between text-xs font-extrabold uppercase tracking-[0.12em] marker:content-none">
                <span>Optional filters</span><span aria-hidden="true">＋</span>
              </summary>
              <div className="pb-1 pt-2">
                <SearchBar leagues={leagues} selectedLeagueIds={selectedLeagueIds} setSelectedLeagueIds={setSelectedLeagueIds} radius={radius} setRadius={setRadius} />
                <label className="mt-3 flex min-h-11 cursor-pointer items-center gap-2 border-t border-[var(--tt-rule)] pt-3 text-xs font-bold text-[var(--tt-muted)]">
                  <input type="checkbox" checked={showAllStadiums} onChange={(event) => setShowAllStadiums(event.target.checked)} className="h-4 w-4 accent-[var(--tt-blue)]" />
                  <span>Show stadiums without fixtures</span>
                </label>
              </div>
            </details>

            <button type="submit" disabled={loading || locationLoading} className="tt-action mt-2 w-full px-5 disabled:cursor-not-allowed disabled:opacity-60 sm:ml-auto sm:block sm:w-auto sm:min-w-40">{loading ? "Searching…" : "Search"}</button>

            {locationError && <p role="alert" className="mt-3 border-l-4 border-[var(--tt-blue)] bg-[var(--tt-newsprint)] p-3 text-sm font-semibold normal-case tracking-normal">{locationError}</p>}
            {dateError && <p role="alert" className="mt-3 border-l-4 border-[var(--tt-blue)] bg-[var(--tt-newsprint)] p-3 text-sm font-semibold normal-case tracking-normal">{dateError}</p>}
          </form>
        )}
      </section>

      {/* Map */}

      {appliedSearch && (
          <section className="mb-5 w-full min-w-0 max-w-full overflow-x-clip" aria-label={`Matches near ${appliedSearch.locationName.split(",")[0]}`}>
            <div className="border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] p-1.5">
<FixtureMap
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
  userLocation={userLocation}
  selectedFixtureId={selectedFixtureId}
  onFixtureSelect={setSelectedFixtureId}
  showDistance={appliedSearch.mode !== "viewport"}
/>
            </div>
            <NearbyFixtureCarousel
              fixtures={visibleFixtures}
              showDistance={appliedSearch.mode !== "viewport"}
              totalMatches={appliedSearch.totalMatches}
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
        <p role="alert" className="border-l-4 border-[var(--tt-blue)] bg-[var(--tt-paper)] p-3 text-sm font-semibold">{discoveryError}</p>
      )}

      {!loading &&
        !dateError &&
        !discoveryError &&
        hasCompletedDiscovery &&
        visibleFixtures.length === 0 && (
          <div className="tt-panel border-l-[8px] border-l-[var(--tt-blue)] p-5"><p className="font-semibold">No fixtures found.</p><p className="mt-1 text-sm text-[var(--tt-muted)]">Try a wider radius, more leagues, or different dates.</p></div>
        )}

      {loading && (
        <p className="tt-kicker py-4" aria-live="polite">Loading fixtures...</p>
      )}

      <DiscoverShortlist fixtures={shortlistFixtures} updatingFixtureIds={updatingInterestedFixtureIds} onRemove={toggleInterested} />

    </main>
  );
}
