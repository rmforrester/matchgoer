"use client";

import { useEffect, useState } from "react";
import api from "../lib/api";
import dynamic from "next/dynamic";

import SearchBar from "./components/SearchBar";
import type { Fixture } from "./types/fixture";

const USE_TEST_LOCATION = true;

const TEST_LATITUDE = 53.4631;
const TEST_LONGITUDE = -2.2913;

const FixtureMap = dynamic(
  () => import("./components/FixtureMap"),
  { ssr: false }
);

type League = {
  league_id: number;
  league_name: string;
};

type InterestedFixture = {
  interested_id: number;
  fixture_id: number;
  fixture_date: string;
  home_team: string;
  away_team: string;
  venue_id: number;
  venue_name: string | null;
  venue_city: string | null;
};

type Venue = {
  venue_id: number;
  name: string;
  city: string | null;
  latitude: number | null;
  longitude: number | null;
};
export default function Home() {
  // -------------------------
  // State
  // -------------------------

  const [fixtures, setFixtures] =
    useState<Fixture[]>([]);

  const [leagues, setLeagues] =
    useState<League[]>([]);

  const [interestedFixtures, setInterestedFixtures] =
    useState<InterestedFixture[]>([]);

  const [visitedVenueIds, setVisitedVenueIds] =
    useState<number[]>([]);

  const [venues, setVenues] =
  useState<Venue[]>([]);

  const [loading, setLoading] =
    useState(false);

  const [interestedLoading, setInterestedLoading] =
    useState(false);

  const [visitedLoading, setVisitedLoading] =
    useState(false);

  const [sessionReady, setSessionReady] =
    useState(false);

  const [selectedLeague, setSelectedLeague] =
    useState("");

  const [radius, setRadius] =
    useState(50);

  const [startDate, setStartDate] =
    useState("2026-08-01");

  const [endDate, setEndDate] =
    useState("2026-09-30");

  // -------------------------
  // User / test location
  // -------------------------

  const [latitude, setLatitude] =
    useState<number | null>(null);

  const [longitude, setLongitude] =
    useState<number | null>(null);

  // -------------------------
  // Load Interested fixtures
  // -------------------------

  const loadInterestedFixtures = () => {
    setInterestedLoading(true);

    api
      .get("/interested")
      .then((response) => {
        setInterestedFixtures(response.data);
      })
      .catch((error) => {
        console.error(
          "Interested loading error:",
          error
        );
      })
      .finally(() => {
        setInterestedLoading(false);
      });
  };

  // -------------------------
  // Load visited stadiums
  // -------------------------

  const loadVisitedStadiums = () => {
  setVisitedLoading(true);

  api
    .get("/my-reviews")
    .then((response) => {
      const reviews = response.data as {
        venue_id: number | string;
      }[];

      const venueIds = reviews.map(
        (review) => Number(review.venue_id)
      );

      setVisitedVenueIds(venueIds);
    })
    .catch((error) => {
      console.error(
        "Visited stadiums loading error:",
        error
      );
    })
    .finally(() => {
      setVisitedLoading(false);
    });
};

  // -------------------------
  // Toggle Interested
  // -------------------------

  const toggleInterested = (
    event: React.MouseEvent,
    fixtureId: number
  ) => {
    event.stopPropagation();

    const isInterested =
      interestedFixtures.some(
        (fixture) =>
          fixture.fixture_id === fixtureId
      );

    if (isInterested) {
      api
        .delete(
          `/fixtures/${fixtureId}/interested`
        )
        .then(() => {
          setInterestedFixtures((current) =>
            current.filter(
              (fixture) =>
                fixture.fixture_id !== fixtureId
            )
          );
        })
        .catch((error) => {
          console.error(
            "Remove Interested error:",
            error
          );
        });

      return;
    }

    api
      .post(
        `/fixtures/${fixtureId}/interested`
      )
      .then(() => {
        loadInterestedFixtures();
      })
      .catch((error) => {
        console.error(
          "Add Interested error:",
          error
        );
      });
  };

  // -------------------------
  // Load nearby fixtures
  // -------------------------

  const loadFixtures = () => {
    if (
      latitude === null ||
      longitude === null
    ) {
      return;
    }

    setLoading(true);

    api
      .get("/nearby", {
        params: {
          latitude,
          longitude,
          radius,
          start_date: startDate,
          end_date: endDate,
          league:
            selectedLeague || undefined,
        },
      })
      .then((response) => {
        setFixtures(response.data);
      })
      .catch((error) => {
        console.error(
          "Fixture loading error:",
          error
        );
      })
      .finally(() => {
        setLoading(false);
      });
  };

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

useEffect(() => {
  if (
    latitude === null ||
    longitude === null
  ) {
    return;
  }

  api
    .get("/venues", {
      params: {
        latitude,
        longitude,
        radius,
        limit: 100,
      },
    })
    .then((response) => {
      setVenues(response.data);
    })
    .catch((error) => {
      console.error(
        "Venue loading error:",
        error
      );
    });
}, [
  latitude,
  longitude,
  radius,
]);
  // -------------------------
  // Load user-specific data
  // session is ready
  // -------------------------

  useEffect(() => {
    if (!sessionReady) {
      return;
    }

    loadInterestedFixtures();
    loadVisitedStadiums();
  }, [sessionReady]);

  // -------------------------
  // Get location
  // -------------------------

  useEffect(() => {
    // Development/testing location
    if (USE_TEST_LOCATION) {
      setLatitude(TEST_LATITUDE);
      setLongitude(TEST_LONGITUDE);
      return;
    }

    // Production browser location
    if (!navigator.geolocation) {
      console.log(
        "Geolocation not supported."
      );
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLatitude(
          position.coords.latitude
        );

        setLongitude(
          position.coords.longitude
        );
      },
      () => {
        console.log(
          "Unable to get location."
        );
      }
    );
  }, []);

  // -------------------------
  // Load fixtures when
  // location changes
  // -------------------------

  useEffect(() => {
    if (
      latitude === null ||
      longitude === null
    ) {
      return;
    }

    loadFixtures();
  }, [latitude, longitude]);

  // -------------------------
  // UI
  // -------------------------

  return (
    <main className="max-w-6xl mx-auto p-6">

      <SearchBar
        leagues={leagues}
        selectedLeague={selectedLeague}
        setSelectedLeague={setSelectedLeague}
        radius={radius}
        setRadius={setRadius}
        startDate={startDate}
        setStartDate={setStartDate}
        endDate={endDate}
        setEndDate={setEndDate}
        onSearch={loadFixtures}
        loading={loading}
      />

      {/* Map */}

      {latitude !== null &&
        longitude !== null && (
          <section className="mb-8">
<FixtureMap
  fixtures={fixtures}
  venues={venues}
  latitude={latitude}
  longitude={longitude}
  visitedVenueIds={visitedVenueIds}
/>
          </section>
        )}

      {!loading &&
        fixtures.length === 0 && (
          <p>No fixtures found.</p>
        )}

      {loading && (
        <p>Loading fixtures...</p>
      )}

      {/* Fixture list */}

      {!loading &&
        fixtures.map((fixture) => {
          const isInterested =
            interestedFixtures.some(
              (item) =>
                item.fixture_id ===
                fixture.fixture_id
            );

          const isVisited =
            visitedVenueIds.includes(
              fixture.venue_id
            );

          return (
            <div
              key={fixture.fixture_id}
              className="border rounded-xl p-5 mb-4 shadow cursor-pointer hover:bg-gray-100"
              onClick={() =>
                (window.location.href =
                  `/venue/${fixture.venue_id}`)
              }
            >
              <div className="flex justify-between items-start gap-4">

                <div>
                  <h2 className="text-xl font-semibold">
                    {fixture.home_team} vs{" "}
                    {fixture.away_team}
                  </h2>

                  <p>
                    {fixture.venue_name}
                  </p>

                  <p>
                    {fixture.venue_city}
                  </p>

                  <p>
                    {new Date(
                      fixture.fixture_date
                    ).toLocaleDateString()}
                  </p>

                  <p>
                    {fixture.distance_miles} miles away
                  </p>

                  {isVisited && (
                    <p className="text-sm font-medium mt-2">
                      ✓ Visited
                    </p>
                  )}
                </div>

                <button
                  type="button"
                  onClick={(event) =>
                    toggleInterested(
                      event,
                      fixture.fixture_id
                    )
                  }
                  className="border rounded-lg px-3 py-2 whitespace-nowrap hover:bg-gray-200"
                >
                  {isInterested
                    ? "★ Interested"
                    : "☆ Interested"}
                </button>

              </div>
            </div>
          );
        })}

    </main>
  );
}