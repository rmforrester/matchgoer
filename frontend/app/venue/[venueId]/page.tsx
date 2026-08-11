"use client";

import { use, useEffect, useState } from "react";
import api from "../../../lib/api";

import VenueHeader from "../../components/VenueHeader";
import AwayDayScore from "../../components/AwayDayScore";
import MatchdayTips from "../../components/MatchdayTips";

type Venue = {
  venue_id: number;
  name: string;
  city: string;
  country: string;
  capacity: number;
};

type Tip = {
  tip_id: number;
  venue_id: number;
  tip: string;
  helpful_votes: number;
  report_count: number;
  status: string;
  created_at: string;
};

type AwayDayScoreData = {
  away_day_score: number | null;
  review_count: number;
  recommend_percentage: number | null;
  category_scores: {
    overall_experience: number | null;
    atmosphere: number | null;
    pubs_restaurants: number | null;
    getting_there: number | null;
    stadium_food_facilities: number | null;
  };
};

type VenueFixture = {
  fixture_id: number;
  fixture_date: string;
  home_team: string;
  away_team: string;
  league_name: string;
  interested_count: number;
};

type MyReview = {
  review_id: number;
  venue_id: number;
  venue_name: string;
  venue_city: string | null;
  fixture_id: number | null;
  fixture_date: string | null;
  home_team: string | null;
  away_team: string | null;
  visit_date: string | null;
  recommend: boolean | null;
  overall_score: number | null;
  atmosphere_score: number | null;
  pubs_score: number | null;
  getting_there_score: number | null;
  facilities_score: number | null;
  created_at: string;
};

type Props = {
  params: Promise<{
    venueId: string;
  }>;
};

export default function VenuePage({
  params,
}: Props) {
  const { venueId } = use(params);

  const [venue, setVenue] =
    useState<Venue | null>(null);

  const [tips, setTips] =
    useState<Tip[]>([]);

  const [awayDayScore, setAwayDayScore] =
    useState<AwayDayScoreData | null>(null);

  const [myReview, setMyReview] =
    useState<MyReview | null>(null);

const [venueFixtures, setVenueFixtures] =
  useState<VenueFixture[]>([]);

const [interestedFixtureIds, setInterestedFixtureIds] =
  useState<number[]>([]);

  const [loading, setLoading] =
    useState(true);

  useEffect(() => {
  setLoading(true);

  // -------------------------------------------------
  // Establish anonymous session first
  // -------------------------------------------------

  api
    .get("/session")
    .then(() => {
      // -------------------------------------------------
      // Load venue
      // -------------------------------------------------

      return api
        .get(`/venue/${venueId}`)
        .then((response) => {
          setVenue(response.data);
        });
    })
    .then(() => {
      // -------------------------------------------------
      // Load matchday tips
      // -------------------------------------------------

      return api
        .get(`/venues/${venueId}/tips`)
        .then((response) => {
          setTips(response.data);
        });
    })
    .then(() => {
      // -------------------------------------------------
      // Load Away Day Score
      // -------------------------------------------------

      return api
        .get(
          `/venues/${venueId}/away-day-score`
        )
        .then((response) => {
          console.log(
            "AWAY DAY SCORE RESPONSE:",
            response.data
          );

          setAwayDayScore(
            response.data
          );
        });
    })
    .then(() => {

// -------------------------------------------------
// Load venue fixtures
// -------------------------------------------------

api
  .get(
    `/venues/${venueId}/fixtures`
  )
  .then((response) => {
    setVenueFixtures(
      response.data
    );
  })
  .catch((error) => {
    console.error(
      "Venue fixtures loading error:",
      error
    );
  });

  // -------------------------------------------------
// Load user's interested fixtures
// -------------------------------------------------

api
  .get("/interested")
  .then((response) => {
    const fixtureIds = response.data.map(
      (fixture: {
        fixture_id: number;
      }) =>
        Number(fixture.fixture_id)
    );

    setInterestedFixtureIds(
      fixtureIds
    );
  })
  .catch((error) => {
    console.error(
      "Interested fixtures loading error:",
      error
    );
  });
      // -------------------------------------------------
      // Load user's stadium reviews
      // -------------------------------------------------

      return api
        .get("/my-reviews")
        .then((response) => {
          const reviews: MyReview[] =
            response.data;

          const currentReview =
            reviews.find(
              (review) =>
                Number(review.venue_id) ===
                Number(venueId)
            );

          setMyReview(
            currentReview ?? null
          );
        });
    })
    .catch((error) => {
      console.error(
        "Venue page loading error:",
        error
      );
    })
    .finally(() => {
      setLoading(false);
    });
}, [venueId]);

  if (loading) {
    return (
      <main
        style={{
          padding: "40px",
        }}
      >
        Loading...
      </main>
    );
  }

  if (!venue) {
    return (
      <main
        style={{
          padding: "40px",
        }}
      >
        Stadium not found.
      </main>
    );
  }

  // -------------------------------------------------
  // Determine user's review status
  // -------------------------------------------------

  const hasVisited =
    myReview !== null;

  const hasCompletedReview =
    myReview !== null &&
    myReview.recommend !== null &&
    myReview.atmosphere_score !== null &&
    myReview.pubs_score !== null &&
    myReview.getting_there_score !== null &&
    myReview.facilities_score !== null;

  return (
    <main
      style={{
        padding: "40px",
        maxWidth: "900px",
        margin: "0 auto",
      }}
    >

<VenueHeader
  venue={venue}
  hasVisited={hasVisited}
  hasCompletedReview={hasCompletedReview}
  onAddStadium={() => {
    window.location.href =
      "/my-stadiums";
  }}
  onCompleteReview={() => {
    window.location.href =
      `/my-stadiums?review=${venueId}`;
  }}
  onEditReview={() => {
    window.location.href =
      `/my-stadiums?review=${venueId}`;
  }}
/>


      <hr />

 <AwayDayScore
  score={
    awayDayScore?.away_day_score ??
    undefined
  }
  reviewCount={
    awayDayScore?.review_count
  }
  recommendPercentage={
    awayDayScore?.recommend_percentage
  }
  categoryScores={
    awayDayScore?.category_scores
  }
  myScore={
    myReview?.overall_score ?? null
  }
/>

      <hr />

      <MatchdayTips
        tips={tips}
      />

      {/* -------------------------------------------------
    UPCOMING FIXTURES
------------------------------------------------- */}

<div
  style={{
    marginTop: "32px",
  }}
>
  <h2
    style={{
      fontSize: "24px",
      fontWeight: "800",
      marginBottom: "16px",
      color: "#fff",
    }}
  >
    📅 Upcoming Fixtures
  </h2>

  {venueFixtures.filter(
    (fixture) =>
      new Date(fixture.fixture_date) >=
      new Date()
  ).length === 0 ? (
    <p
      style={{
        color: "#fff",
      }}
    >
      No upcoming fixtures found.
    </p>
  ) : (
    venueFixtures
      .filter(
        (fixture) =>
          new Date(fixture.fixture_date) >=
          new Date()
      )
      .map((fixture) => {
        const isInterested =
          interestedFixtureIds.includes(
            Number(fixture.fixture_id)
          );

        const fixtureDate =
          new Date(
            fixture.fixture_date
          );

        return (
          <div
            key={fixture.fixture_id}
            style={{
              border: "1px solid #ddd",
              borderRadius: "12px",
              padding: "18px",
              marginBottom: "12px",
              background: "#fff",
            }}
          >

            <p
              style={{
                margin: "0 0 6px 0",
                fontSize: "14px",
                color: "#666",
                fontWeight: "600",
              }}
            >
              {fixtureDate.toLocaleDateString(
                undefined,
                {
                  weekday: "long",
                  day: "numeric",
                  month: "long",
                }
              )}
            </p>

            <h3
              style={{
                margin: "0 0 8px 0",
                fontSize: "19px",
                fontWeight: "800",
                color: "#111827",
              }}
            >
              {fixture.home_team} vs{" "}
              {fixture.away_team}
            </h3>

            <p
              style={{
                margin: "0 0 12px 0",
                color: "#555",
              }}
            >
              🏟️ {venue.name}
            </p>

            <p
              style={{
                margin: "0 0 14px 0",
                fontSize: "14px",
                color: "#555",
              }}
            >
              {fixture.interested_count}{" "}
              {fixture.interested_count === 1
                ? "Terrace Talk user"
                : "Terrace Talk users"}{" "}
              interested
            </p>

            <button
              type="button"
onClick={() => {
  if (isInterested) {

    api
      .delete(
        `/fixtures/${fixture.fixture_id}/interested`
      )
      .then(() => {

        setInterestedFixtureIds(
          (current) =>
            current.filter(
              (id) =>
                id !== fixture.fixture_id
            )
        );

        setVenueFixtures(
          (current) =>
            current.map(
              (item) =>
                item.fixture_id ===
                fixture.fixture_id
                  ? {
                      ...item,
                      interested_count:
                        Math.max(
                          0,
                          item.interested_count - 1
                        ),
                    }
                  : item
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
      `/fixtures/${fixture.fixture_id}/interested`
    )
    .then(() => {

      setInterestedFixtureIds(
        (current) => [
          ...current,
          fixture.fixture_id,
        ]
      );

      setVenueFixtures(
        (current) =>
          current.map(
            (item) =>
              item.fixture_id ===
              fixture.fixture_id
                ? {
                    ...item,
                    interested_count:
                      item.interested_count + 1,
                  }
                : item
          )
      );

    })
    .catch((error) => {
      console.error(
        "Add Interested error:",
        error
      );
    });
}}
              style={{
                border: "1px solid #111827",
                borderRadius: "8px",
                padding: "9px 14px",
                background: isInterested
                  ? "#111827"
                  : "#fff",
                color: isInterested
                  ? "#fff"
                  : "#111827",
                fontWeight: "600",
cursor: "pointer",
              }}
            >
              {isInterested
                ? "★ Interested"
                : "☆ Interested"}
            </button>

          </div>
        );
      })
  )}
</div>

    </main>
  );
}