"use client";

import { useEffect, useState } from "react";
import api from "../../lib/api";

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

export default function InterestedPage() {
  const [fixtures, setFixtures] = useState<InterestedFixture[]>([]);
  const [loading, setLoading] = useState(true);

  const loadInterestedFixtures = () => {
    setLoading(true);

    api
      .get("/interested")
      .then((response) => {
        setFixtures(response.data);
      })
      .catch((error) => {
        console.error(
          "Interested loading error:",
          error
        );
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    loadInterestedFixtures();
  }, []);

  const removeInterested = (
    fixtureId: number
  ) => {
    api
      .delete(
        `/fixtures/${fixtureId}/interested`
      )
      .then(() => {
        setFixtures((current) =>
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
  };

  return (
    <main className="p-8 max-w-4xl mx-auto">

      <div className="flex justify-between items-center mb-8">

        <h1 className="text-4xl font-bold">
          ⭐ Interested
        </h1>

        <button
          type="button"
          onClick={() =>
            (window.location.href = "/")
          }
          className="border rounded-lg px-4 py-2 hover:bg-gray-100"
        >
          Back to fixtures
        </button>

      </div>

      {loading && (
        <p>Loading your fixtures...</p>
      )}

      {!loading &&
        fixtures.length === 0 && (
          <div className="border rounded-xl p-8 text-center">
            <h2 className="text-xl font-semibold mb-2">
              No interested fixtures yet
            </h2>

            <p className="text-gray-600 mb-6">
              Save fixtures you're interested in
              and they'll appear here.
            </p>

            <button
              type="button"
              onClick={() =>
                (window.location.href = "/")
              }
              className="border rounded-lg px-4 py-2 hover:bg-gray-100"
            >
              Find fixtures
            </button>
          </div>
        )}

      {!loading &&
        fixtures.map((fixture) => (
          <div
            key={fixture.fixture_id}
            className="border rounded-xl p-5 mb-4 shadow"
          >

            <div className="flex justify-between items-start gap-4">

              <div
                className="cursor-pointer"
                onClick={() =>
                  (window.location.href =
                    `/venue/${fixture.venue_id}`)
                }
              >

                <h2 className="text-xl font-semibold">
                  {fixture.home_team} vs{" "}
                  {fixture.away_team}
                </h2>

                <p className="mt-2">
                  {fixture.venue_name}
                </p>

                <p>
                  {fixture.venue_city}
                </p>

                <p className="mt-2">
                  {new Date(
                    fixture.fixture_date
                  ).toLocaleDateString(
                    undefined,
                    {
                      weekday: "long",
                      month: "long",
                      day: "numeric",
                      year: "numeric",
                    }
                  )}
                </p>

              </div>

              <button
                type="button"
                onClick={() =>
                  removeInterested(
                    fixture.fixture_id
                  )
                }
                className="border rounded-lg px-3 py-2 whitespace-nowrap hover:bg-gray-100"
              >
                ★ Remove
              </button>

            </div>

          </div>
        ))}
    </main>
  );
}