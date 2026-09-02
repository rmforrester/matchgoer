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
  groupFixturesByVenue,
  hasMeaningfulMapMovement,
  type DiscoveryViewport,
  type FixtureVenueGroup,
} from "../../lib/fixtureDiscovery";
import { createGroundMarkerIcon, createUserLocationIcon } from "./groundMarkerIcon";
import { fixtureStatusGroup, fixtureStatusLabel } from "../../lib/fixture-status";
import { configuredDiscoverTileLayer } from "../../lib/discoverMapTiles";

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
  showDistance: boolean;
};

export type MapSearchArea = DiscoveryViewport;

type FixtureVenueMarkerProps = {
  group: FixtureVenueGroup;
  visited: boolean;
  icon: L.DivIcon;
  onFixtureSelect: (fixtureId: number) => void;
  showDistance: boolean;
};

function FixtureVenueMarker({ group, visited, icon, onFixtureSelect, showDistance }: FixtureVenueMarkerProps) {
  const map = useMap();
  const [fixtureIndex, setFixtureIndex] = useState(0);
  const fixture = group.fixtures[fixtureIndex];
  const fixtureCount = group.fixtures.length;
  const card = compactFixtureCard(fixture);
  const move = (offset: number) => setFixtureIndex((current) => {
    const next = (current + offset + fixtureCount) % fixtureCount;
    onFixtureSelect(group.fixtures[next].fixture_id);
    return next;
  });
  const markerLabel = `${fixture.home_team} versus ${fixture.away_team} at ${fixture.venue_name}${visited ? ", visited ground" : ""}`;
  const statusGroup = fixtureStatusGroup(fixture.status);

  return <Marker position={[fixture.latitude, fixture.longitude]} icon={icon} title={markerLabel} alt={markerLabel} eventHandlers={{ popupopen: () => { setFixtureIndex(0); onFixtureSelect(group.fixtures[0].fixture_id); } }}>
    <Popup closeButton={false} offset={[0, -8]} {...FIXTURE_POPUP_BEHAVIOR} className="tt-fixture-popup">
      <button type="button" onClick={() => map.closePopup()} aria-label="Close fixture details" className="absolute right-2 top-2 grid min-h-9 min-w-9 place-items-center border border-[var(--tt-ink)] text-lg font-bold leading-none">×</button>
      <div className="pr-10">
      <strong className="block leading-tight">{card.matchup}</strong>
      <span className="mt-2 block text-xs font-bold">
      {statusGroup === "postponed" || statusGroup === "cancelled"
        ? fixtureStatusLabel(fixture.status)
        : <>{new Date(fixture.fixture_date).toLocaleDateString()} · {new Date(fixture.fixture_date).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</>}
      </span>
      <span className="mt-1 block text-[0.68rem] font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)]">{fixture.league_name}</span>
      <span className="mt-1 block truncate text-xs font-bold">{fixture.venue_name}</span>
      {showDistance && Number.isFinite(fixture.distance_miles) && <span className="mt-1 block text-xs text-[var(--tt-muted)]">{fixture.distance_miles.toFixed(1)} mi away</span>}
      </div>
      {fixtureCount > 1 && <div className="mt-3 flex items-center justify-between gap-3" aria-label="Fixtures at this stadium">
        <button type="button" onClick={() => move(-1)} aria-label="Previous fixture" className="min-h-11 px-2 text-lg">←</button>
        <span>{fixtureIndex + 1} of {fixtureCount}</span>
        <button type="button" onClick={() => move(1)} aria-label="Next fixture" className="min-h-11 px-2 text-lg">→</button>
      </div>}
      <div><Link href={card.href} className="mt-2 inline-flex min-h-10 items-center text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)] underline decoration-2 underline-offset-4">View match →</Link></div>
    </Popup>
  </Marker>;
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
  showDistance,
}: Props) {
  const fixtureGroups = useMemo(() => groupFixturesByVenue(fixtures), [fixtures]);
  const tileLayer = useMemo(() => configuredDiscoverTileLayer(), []);
  const [areaSearchAvailable, setAreaSearchAvailable] = useState(false);
  const [tileError, setTileError] = useState(false);
  const [selectedMarkerKey, setSelectedMarkerKey] = useState<string | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const suppressMovementRef = useRef(false);
  const groundIcon = useMemo(() => createGroundMarkerIcon(false), []);
  const visitedGroundIcon = useMemo(() => createGroundMarkerIcon(true), []);
  const selectedGroundIcon = useMemo(() => createGroundMarkerIcon(false, true), []);
  const selectedVisitedGroundIcon = useMemo(() => createGroundMarkerIcon(true, true), []);
  const userLocationIcon = useMemo(() => createUserLocationIcon(), []);

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
        return <FixtureVenueMarker key={group.key} group={group} visited={visited} icon={selected ? (visited ? selectedVisitedGroundIcon : selectedGroundIcon) : (visited ? visitedGroundIcon : groundIcon)} onFixtureSelect={onFixtureSelect} showDistance={showDistance} />;
      })}

    </MapContainer>
    {areaSearchAvailable && <button type="button" disabled={searchingArea} onClick={async () => {
      if (!mapRef.current) return;
      const area = currentMapArea(mapRef.current);
      const liveCenter = area.center;
      console.info("[discovery] Search this area pressed", { appliedCenter: { latitude, longitude }, liveCenter });
      console.assert(hasMeaningfulMapMovement({ latitude, longitude }, liveCenter, radius), "Search this area must use a meaningfully changed live map center");
      await onSearchArea(area);
      setAreaSearchAvailable(false);
    }} className="tt-action tt-map-search-action absolute left-1/2 top-3 z-[1000] -translate-x-1/2 shadow-[2px_2px_0_var(--tt-ink)] disabled:opacity-60">{searchingArea ? "Searching…" : "Search this area"}</button>}
    {tileError && <p role="status" className="absolute bottom-3 left-3 right-3 z-[1000] border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] p-3 text-sm font-semibold">The map background could not load. Fixture cards and ground links are still available below.</p>}
</div>
  );
}
