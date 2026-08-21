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
  groupFixturesByVenue,
  hasMeaningfulMapMovement,
  type DiscoveryViewport,
  type FixtureVenueGroup,
} from "../../lib/fixtureDiscovery";
import { createGroundMarkerIcon } from "./groundMarkerIcon";
import { fixtureStatusGroup, fixtureStatusLabel } from "../../lib/fixture-status";

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
};

export type MapSearchArea = DiscoveryViewport;

type FixtureVenueMarkerProps = {
  group: FixtureVenueGroup;
  visited: boolean;
  icon: L.DivIcon;
};

function FixtureVenueMarker({ group, visited, icon }: FixtureVenueMarkerProps) {
  const map = useMap();
  const [fixtureIndex, setFixtureIndex] = useState(0);
  const fixture = group.fixtures[fixtureIndex];
  const fixtureCount = group.fixtures.length;
  const move = (offset: number) => setFixtureIndex((current) => (current + offset + fixtureCount) % fixtureCount);
  const markerLabel = `${fixture.home_team} versus ${fixture.away_team} at ${fixture.venue_name}${visited ? ", visited ground" : ""}`;
  const statusGroup = fixtureStatusGroup(fixture.status);

  return <Marker position={[fixture.latitude, fixture.longitude]} icon={icon} title={markerLabel} alt={markerLabel} eventHandlers={{ popupopen: () => setFixtureIndex(0) }}>
    <Popup closeButton={false} autoPan={false}>
      <div className="mb-2 flex justify-end"><button type="button" onClick={() => map.closePopup()} aria-label="Close fixture details" className="min-h-11 min-w-11 border border-[var(--tt-ink)] text-lg font-bold leading-none">×</button></div>
      <strong>{fixture.home_team}</strong><br />vs<br /><strong>{fixture.away_team}</strong>
      <br /><br /><strong>{fixture.venue_name}</strong>
      {fixture.venue_city && <><br />{fixture.venue_city}</>}
      <br /><br />
      {statusGroup === "postponed" || statusGroup === "cancelled"
        ? fixtureStatusLabel(fixture.status)
        : <>{new Date(fixture.fixture_date).toLocaleDateString()} · {new Date(fixture.fixture_date).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</>}
      <br />{fixture.distance_miles} miles away
      {fixtureCount > 1 && <div className="mt-3 flex items-center justify-between gap-3" aria-label="Fixtures at this stadium">
        <button type="button" onClick={() => move(-1)} aria-label="Previous fixture" className="min-h-11 px-2 text-lg">←</button>
        <span>{fixtureIndex + 1} of {fixtureCount}</span>
        <button type="button" onClick={() => move(1)} aria-label="Next fixture" className="min-h-11 px-2 text-lg">→</button>
      </div>}
      <div><Link href={`/fixture/${fixture.fixture_id}`} className="mt-3 inline-flex min-h-11 items-center font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)] underline decoration-2 underline-offset-4">View match →</Link></div>
      {visited && <><br /><br /><strong>✓ You&apos;ve visited this stadium</strong></>}
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
}: Props) {
  const fixtureGroups = useMemo(() => groupFixturesByVenue(fixtures), [fixtures]);
  const [areaSearchAvailable, setAreaSearchAvailable] = useState(false);
  const [tileError, setTileError] = useState(false);
  const mapRef = useRef<L.Map | null>(null);
  const suppressMovementRef = useRef(false);
  const groundIcon = useMemo(() => createGroundMarkerIcon(false), []);
  const visitedGroundIcon = useMemo(() => createGroundMarkerIcon(true), []);

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
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        eventHandlers={{ tileerror: () => setTileError(true), load: () => setTileError(false) }}
      />


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

        return (
          <Marker
            key={`venue-${venueId}`}
            position={[
              venue.latitude,
              venue.longitude,
            ]}
            icon={visited ? visitedGroundIcon : groundIcon}
            title={`${venue.name}${visited ? ", visited ground" : ""}`}
            alt={`${venue.name}${visited ? ", visited ground" : ""}`}
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
        return <FixtureVenueMarker key={group.key} group={group} visited={visited} icon={visited ? visitedGroundIcon : groundIcon} />;
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
    }} className="tt-action absolute left-1/2 top-4 z-[1000] -translate-x-1/2 px-5 shadow-[3px_3px_0_var(--tt-ink)] disabled:opacity-60">{searchingArea ? "Searching…" : "Search this area"}</button>}
    {tileError && <p role="status" className="absolute bottom-3 left-3 right-3 z-[1000] border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] p-3 text-sm font-semibold">The map background could not load. Fixture cards and ground links are still available below.</p>}
</div>
  );
}
