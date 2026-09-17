"use client";

import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  useMap,
  useMapEvents,
} from "react-leaflet";

import L from "leaflet";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";

import "leaflet/dist/leaflet.css";

import type { Fixture } from "../types/fixture";
import {
  discoveryZoomForRadius,
  compactFixtureCard,
  FIXTURE_POPUP_BEHAVIOR,
  fixtureGroupDecision,
  groupFixturesByVenue,
  hasMeaningfulMapMovement,
  type DiscoveryViewport,
  type FixtureVenueGroup,
} from "../../lib/fixtureDiscovery";
import { createGroundMarkerIcon, createUserLocationIcon } from "./groundMarkerIcon";
import { fixtureStatusGroup, fixtureStatusLabel } from "../../lib/fixture-status";
import { configuredDiscoverTileLayer } from "../../lib/discoverMapTiles";
import { fixtureTypeLabel, safeFixtureType, type FixtureType } from "../../lib/fixtureType";

type Venue = {
  venue_id: number;
  name: string;
  city: string | null;
  latitude: number | null;
  longitude: number | null;
};

type Props = {
  fixtures: Fixture[];
  venues: Venue[];
  latitude: number;
  longitude: number;
  visitedVenueIds: number[];
  showAllStadiums: boolean;
  radius: number;
  viewportLatitude: number;
  viewportLongitude: number;
  viewportRevision: number;
  searchingArea: boolean;
  onViewportReady: (area: MapSearchArea) => void;
  onSearchArea: (area: MapSearchArea) => Promise<void>;
  userLocation: { latitude: number; longitude: number } | null;
  selectedFixtureId: number | null;
  onFixtureSelect: (fixtureId: number) => void;
  onFixtureDismiss: (fixtureId: number) => void;
  showDistance: boolean;
};

export type MapSearchArea = DiscoveryViewport;

type FixtureVenueMarkerProps = {
  group: FixtureVenueGroup;
  visited: boolean;
  icons: Record<FixtureType, L.DivIcon>;
  onFixtureSelect: (fixtureId: number) => void;
  onFixtureDismiss: (fixtureId: number) => void;
  showDistance: boolean;
  compactMobile: boolean;
};

function FixtureTypeIcon({ type }: { type: FixtureType }) {
  if (type === "standard") return null;
  return <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center" aria-label={fixtureTypeLabel(type)} title={fixtureTypeLabel(type)}>
    {type === "cup"
      ? <svg aria-hidden="true" viewBox="0 0 16 16" className="h-3.5 w-3.5"><path d="M4 2H12V4.5C12 7.2 10.5 9 8 9C5.5 9 4 7.2 4 4.5V2ZM4 3H2V4.2C2 5.8 3 6.8 4.7 6.9M12 3H14V4.2C14 5.8 13 6.8 11.3 6.9M8 9V12M5 13H11" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="square" strokeLinejoin="miter"/></svg>
      : <svg aria-hidden="true" viewBox="0 0 16 16" className="h-3.5 w-3.5"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.5"/><path d="M2.5 8H13.5M8 2C9.6 3.7 10.3 5.7 10.3 8C10.3 10.3 9.6 12.3 8 14M8 2C6.4 3.7 5.7 5.7 5.7 8C5.7 10.3 6.4 12.3 8 14" fill="none" stroke="currentColor" strokeWidth="1.1"/></svg>}
  </span>;
}

function FixtureVenueMarker({ group, visited, icons, onFixtureSelect, onFixtureDismiss, showDistance, compactMobile }: FixtureVenueMarkerProps) {
  const map = useMap();
  const decision = fixtureGroupDecision(group.fixtures);
  const [fixtureIndex, setFixtureIndex] = useState(decision.initialFixtureIndex);
  const fixture = group.fixtures[fixtureIndex];
  const fixtureType = safeFixtureType(fixture.fixture_type);
  const fixtureCount = group.fixtures.length;
  const card = compactFixtureCard(fixture);
  const move = (offset: number) => setFixtureIndex((current) => {
    const next = (current + offset + fixtureCount) % fixtureCount;
    onFixtureSelect(group.fixtures[next].fixture_id);
    return next;
  });
  const markerLabel = `${fixture.home_team} versus ${fixture.away_team} at ${fixture.venue_name}${visited ? ", visited ground" : ""}`;
  const statusGroup = fixtureStatusGroup(fixture.status);

  return <Marker position={[fixture.latitude, fixture.longitude]} icon={icons[fixtureType]} title={markerLabel} alt={markerLabel} eventHandlers={{ click: () => {
    if (compactMobile) {
      setFixtureIndex(decision.initialFixtureIndex);
      onFixtureSelect(group.fixtures[decision.initialFixtureIndex].fixture_id);
    }
  }, popupopen: () => { setFixtureIndex(decision.initialFixtureIndex); onFixtureSelect(group.fixtures[decision.initialFixtureIndex].fixture_id); }, popupclose: () => onFixtureDismiss(fixture.fixture_id) }}>
    {!compactMobile && <Popup closeButton={false} offset={[0, -8]} {...FIXTURE_POPUP_BEHAVIOR} className="tt-fixture-popup">
      <button type="button" onClick={() => { onFixtureDismiss(fixture.fixture_id); map.closePopup(); }} aria-label="Dismiss selected fixture" className="absolute right-2 top-2 grid min-h-11 min-w-11 place-items-center border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] text-2xl font-bold leading-none">×</button>
      <div className="pr-10">
      {fixture.highlight_eligible && fixture.lead_decision_reason && <div className="tt-fixture-popup-optional mb-2 border-l-4 border-[var(--tt-gold)] pl-3">
        <strong className="line-clamp-2 break-words text-sm leading-tight">{fixture.lead_decision_reason.emoji} {fixture.lead_decision_reason.label}</strong>
      </div>}
      <strong className="block min-w-0 break-words leading-tight">{card.matchup}</strong>
      <span className="mt-2 block text-xs font-bold">
      {statusGroup === "postponed" || statusGroup === "cancelled"
        ? fixtureStatusLabel(fixture.status)
        : <>{new Date(fixture.fixture_date).toLocaleDateString()} · {new Date(fixture.fixture_date).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</>}
      </span>
      <span className="mt-1 flex items-center gap-1 text-[0.68rem] font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)]"><FixtureTypeIcon type={fixtureType} />{fixture.league_name}</span>
      <span className="mt-1 block min-w-0 break-words text-xs font-bold">{fixture.venue_name}</span>
      {showDistance && Number.isFinite(fixture.distance_miles) && <span className="tt-fixture-popup-optional mt-1 block text-xs text-[var(--tt-muted)]">{fixture.distance_miles.toFixed(1)} mi away</span>}
      </div>
      {fixtureCount > 1 && <div className="mt-3 flex items-center justify-between gap-3" aria-label="Fixtures at this stadium">
        <button type="button" onClick={() => move(-1)} aria-label="Previous fixture" className="min-h-11 px-2 text-lg">←</button>
        <span>{fixtureIndex + 1} of {fixtureCount}</span>
        <button type="button" onClick={() => move(1)} aria-label="Next fixture" className="min-h-11 px-2 text-lg">→</button>
      </div>}
      <div><Link href={card.href} className="mt-2 inline-flex min-h-10 items-center text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)] underline decoration-2 underline-offset-4">View match →</Link></div>
    </Popup>}
  </Marker>;
}

function MobileFixtureCard({
  fixture,
  group,
  onFixtureSelect,
  onFixtureDismiss,
}: {
  fixture: Fixture;
  group: FixtureVenueGroup;
  onFixtureSelect: (fixtureId: number) => void;
  onFixtureDismiss: (fixtureId: number) => void;
}) {
  const fixtureIndex = group.fixtures.findIndex((candidate) => candidate.fixture_id === fixture.fixture_id);
  const statusGroup = fixtureStatusGroup(fixture.status);
  const fixtureType = safeFixtureType(fixture.fixture_type);
  const move = (offset: number) => {
    const next = (fixtureIndex + offset + group.fixtures.length) % group.fixtures.length;
    onFixtureSelect(group.fixtures[next].fixture_id);
  };

  return <article className="tt-mobile-fixture-card" aria-label="Selected fixture">
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_2.75rem] gap-3">
      <div className="min-w-0">
        <strong className="block min-w-0 break-words text-base leading-snug">{fixture.home_team} v {fixture.away_team}</strong>
        <span className="mt-1.5 block text-sm font-bold leading-snug">
          {statusGroup === "postponed" || statusGroup === "cancelled"
            ? fixtureStatusLabel(fixture.status)
            : <>{new Date(fixture.fixture_date).toLocaleDateString()} · {new Date(fixture.fixture_date).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</>}
        </span>
        <span className="mt-1 flex min-w-0 items-center gap-1 break-words text-xs font-extrabold uppercase leading-snug tracking-[0.06em] text-[var(--brand-interactive)]"><FixtureTypeIcon type={fixtureType} />{fixture.league_name}</span>
        <span className="mt-1 block min-w-0 break-words text-sm font-bold leading-snug">{fixture.venue_name}</span>
      </div>
      <button type="button" onClick={() => onFixtureDismiss(fixture.fixture_id)} aria-label="Dismiss selected fixture" className="grid h-11 w-11 place-items-center border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] text-2xl font-bold leading-none">×</button>
    </div>
    <div className="mt-2 flex min-w-0 items-center justify-between gap-3">
      <Link href={`/fixture/${fixture.fixture_id}`} className="inline-flex min-h-10 min-w-0 items-center text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)] underline decoration-2 underline-offset-4">View match →</Link>
      {group.fixtures.length > 1 && <div className="flex shrink-0 items-center gap-1" aria-label="Fixtures at this stadium">
        <button type="button" onClick={() => move(-1)} aria-label="Previous fixture" className="grid h-10 w-10 place-items-center text-lg">←</button>
        <span className="text-xs font-bold">{fixtureIndex + 1}/{group.fixtures.length}</span>
        <button type="button" onClick={() => move(1)} aria-label="Next fixture" className="grid h-10 w-10 place-items-center text-lg">→</button>
      </div>}
    </div>
  </article>;
}

function currentMapArea(map: L.Map): MapSearchArea {
  const center = map.getCenter();
  const bounds = map.getBounds();
  return {
    center: { latitude: center.lat, longitude: center.lng },
    north: bounds.getNorth(),
    south: bounds.getSouth(),
    east: bounds.getEast(),
    west: bounds.getWest(),
  };
}

function ViewportController({
  latitude,
  longitude,
  radius,
  revision,
  suppressMovementRef,
  onViewportReady,
}: {
  latitude: number;
  longitude: number;
  radius: number;
  revision: number;
  suppressMovementRef: MutableRefObject<boolean>;
  onViewportReady: (area: MapSearchArea) => void;
}) {
  const map = useMap();
  useEffect(() => {
    if (!revision) return;
    suppressMovementRef.current = true;
    map.setView([latitude, longitude], discoveryZoomForRadius(radius), { animate: false });
    onViewportReady(currentMapArea(map));
    suppressMovementRef.current = false;
  }, [latitude, longitude, map, onViewportReady, radius, revision, suppressMovementRef]);
  return null;
}

function MapMovementMonitor({
  appliedCenter,
  radius,
  suppressMovementRef,
  onCandidateChange,
}: {
  appliedCenter: { latitude: number; longitude: number };
  radius: number;
  suppressMovementRef: MutableRefObject<boolean>;
  onCandidateChange: (moved: boolean) => void;
}) {
  useMapEvents({
    moveend(event) {
      if (suppressMovementRef.current) return;
      const center = event.target.getCenter();
      const candidate = { latitude: center.lat, longitude: center.lng };
      onCandidateChange(hasMeaningfulMapMovement(appliedCenter, candidate, radius));
    },
    zoomend() {
      if (!suppressMovementRef.current) onCandidateChange(true);
    },
  });
  return null;
}

export default function FixtureMap({
  fixtures,
  venues,
  latitude,
  longitude,
  visitedVenueIds = [],
  showAllStadiums,
  radius,
  viewportLatitude,
  viewportLongitude,
  viewportRevision,
  searchingArea,
  onViewportReady,
  onSearchArea,
  userLocation,
  selectedFixtureId,
  onFixtureSelect,
  onFixtureDismiss,
  showDistance,
}: Props) {
  const fixtureGroups = useMemo(() => groupFixturesByVenue(fixtures), [fixtures]);
  const tileLayer = useMemo(() => configuredDiscoverTileLayer(), []);
  const [areaSearchAvailable, setAreaSearchAvailable] = useState(false);
  const [tileError, setTileError] = useState(false);
  const [selectedMarkerKey, setSelectedMarkerKey] = useState<string | null>(null);
  const [compactMobile, setCompactMobile] = useState(false);
  const mapRef = useRef<L.Map | null>(null);
  const suppressMovementRef = useRef(false);
  const groundIcon = useMemo(() => createGroundMarkerIcon(false), []);
  const visitedGroundIcon = useMemo(() => createGroundMarkerIcon(true), []);
  const selectedGroundIcon = useMemo(() => createGroundMarkerIcon(false, true), []);
  const selectedVisitedGroundIcon = useMemo(() => createGroundMarkerIcon(true, true), []);
  const userLocationIcon = useMemo(() => createUserLocationIcon(), []);
  const fixtureIcons = useMemo(() => {
    const icons = {} as Record<string, L.DivIcon>;
    for (const fixtureType of ["standard", "cup", "international"] as const) {
      for (const visited of [false, true]) {
        for (const selected of [false, true]) {
          for (const highlighted of [false, true]) {
            icons[`${fixtureType}-${visited}-${selected}-${highlighted}`] = createGroundMarkerIcon(visited, selected, highlighted, fixtureType);
          }
        }
      }
    }
    return icons;
  }, []);
  const selectedFixtureGroup = useMemo(
    () => selectedFixtureId === null
      ? null
      : fixtureGroups.find((group) => group.fixtures.some((fixture) => fixture.fixture_id === selectedFixtureId)) ?? null,
    [fixtureGroups, selectedFixtureId],
  );
  const selectedFixture = selectedFixtureGroup?.fixtures.find((fixture) => fixture.fixture_id === selectedFixtureId) ?? null;
  useEffect(() => {
    const query = window.matchMedia("(max-width: 640px)");
    const update = () => setCompactMobile(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  // Fixture and venue locations share the same editorial ground marker.


  // ---------------------------------------------------------
  // Identify venues that currently have fixtures
  //
  // Fixture pins take precedence over stadium pins.
  // ---------------------------------------------------------

  const fixtureVenueIds = new Set(
    fixtureGroups.flatMap((group) => group.venueId === null ? [] : [group.venueId])
  );


  // ---------------------------------------------------------
  // Visited helper
  // ---------------------------------------------------------

  const isVisited = (
    venueId: number
  ) => {
    return visitedVenueIds.includes(
      Number(venueId)
    );
  };


  return (
<div className="relative">
<MapContainer
  ref={mapRef}
  center={[latitude, longitude]}
  zoom={discoveryZoomForRadius(radius)}
  closePopupOnClick
      className="tt-map"
    >
      <ViewportController latitude={viewportLatitude} longitude={viewportLongitude} radius={radius} revision={viewportRevision} suppressMovementRef={suppressMovementRef} onViewportReady={onViewportReady} />
      <MapMovementMonitor appliedCenter={{ latitude, longitude }} radius={radius} suppressMovementRef={suppressMovementRef} onCandidateChange={setAreaSearchAvailable} />

      <TileLayer
        {...tileLayer}
        eventHandlers={{ tileerror: () => setTileError(true), load: () => setTileError(false) }}
      />

      {userLocation && <Marker
        position={[userLocation.latitude, userLocation.longitude]}
        icon={userLocationIcon}
        alt="You are here"
        interactive={false}
        keyboard={false}
      />}


      {/* ---------------------------------------------------
          STADIUM PINS

          Only render a stadium pin when there is no
          fixture currently being displayed there.
      --------------------------------------------------- */}

      {showAllStadiums && venues.map((venue) => {

        if (
          venue.latitude === null ||
          venue.longitude === null
        ) {
          return null;
        }

        const venueId =
          Number(venue.venue_id);

        const hasFixture =
          fixtureVenueIds.has(
            venueId
          );

        if (hasFixture) {
          return null;
        }

        const visited =
          isVisited(venueId);
        const markerKey = `venue-${venueId}`;
        const selected = selectedMarkerKey === markerKey;

        return (
          <Marker
            key={markerKey}
            position={[
              venue.latitude,
              venue.longitude,
            ]}
            icon={selected ? (visited ? selectedVisitedGroundIcon : selectedGroundIcon) : (visited ? visitedGroundIcon : groundIcon)}
            title={`${venue.name}${visited ? ", visited ground" : ""}`}
            alt={`${venue.name}${visited ? ", visited ground" : ""}`}
            eventHandlers={{ popupopen: () => setSelectedMarkerKey(markerKey), popupclose: () => setSelectedMarkerKey((current) => current === markerKey ? null : current) }}
          >

            <Popup>

              <strong>
                {venue.name}
              </strong>

              {venue.city && (
                <>
                  <br />
                  {venue.city}
                </>
              )}

              {visited && (
                <>
                  <br />
                  <br />

                  <strong>
                    ✓ You&apos;ve visited this stadium
                  </strong>
                </>
              )}

            </Popup>

          </Marker>
        );
      })}


      {/* ---------------------------------------------------
          FIXTURE PINS

          Football = fixture
          Fixture pins take precedence over stadium pins.
      --------------------------------------------------- */}

      {fixtureGroups.map((group) => {
        const visited = group.venueId !== null && isVisited(group.venueId);
        const selected = group.fixtures.some((fixture) => fixture.fixture_id === selectedFixtureId);
        const highlighted = fixtureGroupDecision(group.fixtures).highlighted;
        const icons = Object.fromEntries(
          (["standard", "cup", "international"] as const).map((fixtureType) => [
            fixtureType,
            fixtureIcons[`${fixtureType}-${visited}-${selected}-${highlighted}`],
          ]),
        ) as Record<FixtureType, L.DivIcon>;
        return <FixtureVenueMarker key={group.key} group={group} visited={visited} icons={icons} onFixtureSelect={onFixtureSelect} onFixtureDismiss={onFixtureDismiss} showDistance={showDistance} compactMobile={compactMobile} />;
      })}

    </MapContainer>
    {areaSearchAvailable && <button type="button" disabled={searchingArea} onClick={async () => {
      if (!mapRef.current) return;
      const area = currentMapArea(mapRef.current);
      const liveCenter = area.center;
      console.info("[discovery] Search this area pressed", { appliedCenter: { latitude, longitude }, liveCenter });
      console.assert(hasMeaningfulMapMovement({ latitude, longitude }, liveCenter, radius), "Search this area must use a meaningfully changed live map center");
      mapRef.current.closePopup();
      if (selectedFixtureId !== null) onFixtureDismiss(selectedFixtureId);
      await onSearchArea(area);
      setAreaSearchAvailable(false);
    }} className="tt-action tt-map-search-action absolute left-1/2 top-3 z-[1000] -translate-x-1/2 shadow-[2px_2px_0_var(--tt-ink)] disabled:opacity-60">{searchingArea ? "Searching…" : "Search this area"}</button>}
    {compactMobile && selectedFixture && selectedFixtureGroup && <div className="tt-mobile-fixture-safe-area">
      <MobileFixtureCard fixture={selectedFixture} group={selectedFixtureGroup} onFixtureSelect={onFixtureSelect} onFixtureDismiss={onFixtureDismiss} />
    </div>}
    {tileError && <p role="status" className="absolute bottom-3 left-3 right-3 z-[1000] border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] p-3 text-sm font-semibold">The map background could not load. Fixture cards and ground links are still available below.</p>}
</div>
  );
}
