"use client";

import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
} from "react-leaflet";

import L from "leaflet";

import "leaflet/dist/leaflet.css";

import type { Fixture } from "../types/fixture";

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
};

export default function FixtureMap({
  fixtures,
  venues,
  latitude,
  longitude,
  visitedVenueIds = [],
}: Props) {

  // ---------------------------------------------------------
  // Stadium pin
  //
  // Blue pin = stadium
  // ---------------------------------------------------------

  const createStadiumIcon = (
    visited: boolean
  ) => {
    return L.divIcon({
      className: "",
      html: `
        <div style="
          position: relative;
          width: 32px;
          height: 42px;
        ">

          <div style="
            width: 30px;
            height: 30px;
            background: #2563eb;
            border: 3px solid white;
            border-radius: 50% 50% 50% 0;
            transform: rotate(-45deg);
            box-shadow: 0 2px 5px rgba(0,0,0,0.3);
            position: absolute;
            top: 0;
            left: 0;
          "></div>

          ${
            visited
              ? `
                <div style="
                  position: absolute;
                  top: -7px;
                  right: -7px;
                  width: 19px;
                  height: 19px;
                  background: white;
                  border: 2px solid #16a34a;
                  border-radius: 50%;
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  color: #16a34a;
                  font-size: 12px;
                  font-weight: 700;
                  z-index: 10;
                ">
                  ✓
                </div>
              `
              : ""
          }

        </div>
      `,
      iconSize: [32, 42],
      iconAnchor: [16, 42],
      popupAnchor: [0, -42],
    });
  };


  // ---------------------------------------------------------
  // Fixture pin
  //
  // Football = fixture occurring at the stadium
  // ---------------------------------------------------------

  const createFixtureIcon = (
    visited: boolean
  ) => {
    return L.divIcon({
      className: "",
      html: `
        <div style="
          position: relative;
          width: 38px;
          height: 38px;
        ">

          <div style="
            width: 34px;
            height: 34px;
            background: white;
            border: 3px solid #111827;
            border-radius: 50%;
            box-shadow: 0 2px 6px rgba(0,0,0,0.35);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            position: absolute;
            top: 0;
            left: 0;
          ">
            ⚽
          </div>

          ${
            visited
              ? `
                <div style="
                  position: absolute;
                  top: -7px;
                  right: -7px;
                  width: 19px;
                  height: 19px;
                  background: white;
                  border: 2px solid #16a34a;
                  border-radius: 50%;
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  color: #16a34a;
                  font-size: 12px;
                  font-weight: 700;
                  z-index: 10;
                ">
                  ✓
                </div>
              `
              : ""
          }

        </div>
      `,
      iconSize: [38, 38],
      iconAnchor: [19, 19],
      popupAnchor: [0, -19],
    });
  };


  // ---------------------------------------------------------
  // Identify venues that currently have fixtures
  //
  // Fixture pins take precedence over stadium pins.
  // ---------------------------------------------------------

  const fixtureVenueIds = new Set(
    fixtures.map(
      (fixture) =>
        Number(fixture.venue_id)
    )
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
    <MapContainer
      center={[latitude, longitude]}
      zoom={8}
      style={{
        height: "600px",
        width: "100%",
        borderRadius: "12px",
      }}
    >

      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />


      {/* ---------------------------------------------------
          STADIUM PINS

          Only render a stadium pin when there is no
          fixture currently being displayed there.
      --------------------------------------------------- */}

      {venues.map((venue) => {

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
            icon={createStadiumIcon(
              visited
            )}
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
                    ✓ You've visited this stadium
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

      {fixtures.map((fixture) => {

        const visited =
          isVisited(
            Number(fixture.venue_id)
          );

        return (
          <Marker
            key={`fixture-${fixture.fixture_id}`}
            position={[
              fixture.latitude,
              fixture.longitude,
            ]}
            icon={createFixtureIcon(
              visited
            )}
          >

            <Popup>

              <strong>
                {fixture.home_team}
              </strong>

              <br />

              vs

              <br />

              <strong>
                {fixture.away_team}
              </strong>

              <br />
              <br />

              <strong>
                {fixture.venue_name}
              </strong>

              {fixture.venue_city && (
                <>
                  <br />
                  {fixture.venue_city}
                </>
              )}

              <br />
              <br />

              {new Date(
                fixture.fixture_date
              ).toLocaleDateString()}

              <br />

              {fixture.distance_miles} miles away

              {visited && (
                <>
                  <br />
                  <br />

                  <strong>
                    ✓ You've visited this stadium
                  </strong>
                </>
              )}

            </Popup>

          </Marker>
        );
      })}

    </MapContainer>
  );
}