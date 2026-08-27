"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import api from "../../../lib/api";

import VenueHeader from "../../components/VenueHeader";
import AwayDayScore from "../../components/AwayDayScore";
import MatchdayTips from "../../components/MatchdayTips";
import VenueGuide from "../../components/VenueGuide";
import type { VenueGuide as VenueGuideData } from "../../../lib/venue-guide";
import AccountConversionPrompt from "../../components/AccountConversionPrompt";
import FixtureTeams from "../../components/FixtureTeams";
import type { MyGround } from "../../types/grounds";
import { fixtureStatusGroup, fixtureStatusLabel } from "../../../lib/fixture-status";

type Venue = {
  venue_id: number;
  name: string;
  city: string;
  country: string;
  capacity: number | null;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
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
  status: string | null;
  interested_count: number;
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
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedTeamId = Number(searchParams.get("teamId"));
  const teamId = Number.isInteger(requestedTeamId) && requestedTeamId > 0 ? requestedTeamId : null;

  const [venue, setVenue] =
    useState<Venue | null>(null);

  const [tips, setTips] =
    useState<Tip[]>([]);

  const [awayDayScore, setAwayDayScore] =
    useState<AwayDayScoreData | null>(null);
  const [guide, setGuide] = useState<VenueGuideData | null>(null);

  const [myGround, setMyGround] =
    useState<MyGround | null>(null);

const [venueFixtures, setVenueFixtures] =
  useState<VenueFixture[]>([]);

const [interestedFixtureIds, setInterestedFixtureIds] =
  useState<number[]>([]);
const [updatingInterestedFixtureIds, setUpdatingInterestedFixtureIds] = useState<number[]>([]);
const [showAccountPrompt, setShowAccountPrompt] = useState(false);

  const [loading, setLoading] =
    useState(true);

  const [addingVisited, setAddingVisited] =
    useState(false);

  const [visitedError, setVisitedError] =
    useState("");

  useEffect(() => {
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
      return api
        .get(`/venues/${venueId}/guide`, { params: { team_id: teamId ?? undefined } })
        .then((response) => {
          setGuide(response.data);
        })
        .catch(() => {
          setGuide(null);
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
        .get("/my-grounds")
        .then((response) => {
          const grounds: MyGround[] =
            response.data;

          const currentGround =
            grounds.find(
              (ground) =>
                Number(ground.venue_id) ===
                Number(venueId)
            );

          setMyGround(
            currentGround ?? null
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
}, [teamId, venueId]);

  if (loading) {
    return <main className="mx-auto w-full max-w-5xl p-4 sm:p-6"><p className="tt-kicker">01 / The ground</p><p className="mt-3 font-semibold">Loading ground…</p></main>;
  }

  if (!venue) {
    return <main className="mx-auto w-full max-w-5xl p-4 sm:p-6"><p className="tt-kicker">01 / The ground</p><h1 className="tt-display mt-2 text-5xl">Ground not found</h1></main>;
  }

  // -------------------------------------------------
  // Determine user's review status
  // -------------------------------------------------

  const hasVisited =
    myGround !== null;

  const reviewState = myGround?.review?.state;

  const openReview = () => {
    router.push(`/my-football?tab=visited&review=${venueId}`);
  };

  const addToVisited = async () => {
    if (addingVisited || myGround !== null) {
      return;
    }

    setAddingVisited(true);
    setVisitedError("");

    try {
      await api.post(`/venues/${venueId}/visits`, {});

      const response = await api.get("/my-grounds");
      const grounds = response.data as MyGround[];
      const currentGround = grounds.find(
        (ground) => Number(ground.venue_id) === Number(venueId)
      );

      if (!currentGround) {
        throw new Error("Visited record was not returned after creation.");
      }

      setMyGround(currentGround);
    } catch (error: unknown) {
      const status =
        typeof error === "object" &&
        error !== null &&
        "response" in error &&
        typeof error.response === "object" &&
        error.response !== null &&
        "status" in error.response
          ? error.response.status
          : undefined;

      if (status === 409) {
        try {
          const response = await api.get("/my-grounds");
          const grounds = response.data as MyGround[];
          const currentGround = grounds.find(
            (ground) => Number(ground.venue_id) === Number(venueId)
          );

          if (currentGround) {
            setMyGround(currentGround);
            return;
          }
        } catch {
          // Use the same user-facing error as other failed add attempts.
        }
      }

      console.error("Add to Visited error:", error);
      setVisitedError("Unable to add this ground to My Grounds.");
    } finally {
      setAddingVisited(false);
    }
  };

  const upcomingFixtures = venueFixtures
    .filter((fixture) => new Date(fixture.fixture_date) >= new Date())
    .sort((left, right) => new Date(left.fixture_date).getTime() - new Date(right.fixture_date).getTime());
  const featuredFixtures = upcomingFixtures.slice(0, 4);

  return (
    <main className="mx-auto w-full min-w-0 max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
      <AccountConversionPrompt open={showAccountPrompt} kind="interested" onDismiss={() => setShowAccountPrompt(false)} />

      <VenueHeader venue={venue} />

      {visitedError && (
        <p role="alert" className="mt-4 border-l-4 border-red-700 bg-[var(--tt-paper)] px-4 py-3 font-semibold text-red-800">{visitedError}</p>
      )}

      {guide && <VenueGuide guide={guide} />}

      <AwayDayScore reviewCount={awayDayScore?.review_count} recommendPercentage={awayDayScore?.recommend_percentage} categoryScores={awayDayScore?.category_scores} />

      <section className="tt-section-rule mt-10 pt-4" aria-labelledby="visit-heading">
        <p className="tt-kicker">03 / Your visit</p>
        <div className="mt-1 grid gap-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
          <div><h2 id="visit-heading" className="tt-display text-4xl leading-none sm:text-5xl">{hasVisited ? "Been here" : "Make it one of yours"}</h2><p className="mt-2 max-w-2xl text-[var(--tt-muted)]">{reviewState === "completed" ? "This ground is in My Grounds and your review is complete." : hasVisited ? `This ground is in My Grounds${myGround && myGround.visit_count > 1 ? ` with ${myGround.visit_count} recorded visits` : ""}. Your rating is optional.` : "Add this ground to My Grounds. You can rate it separately whenever you are ready."}</p></div>
          {!hasVisited ? <button type="button" onClick={addToVisited} disabled={addingVisited} className="tt-action px-5">{addingVisited ? "Adding…" : "Add to My Grounds"}</button> : <button type="button" onClick={openReview} className="tt-action px-5">{reviewState === "completed" ? "Edit my review" : reviewState === "partial" ? "Continue review" : "Rate this ground"}</button>}
        </div>
      </section>

      <MatchdayTips tips={tips} venueId={Number(venueId)} />

      <section className="tt-section-rule mt-10 pt-4" aria-labelledby="fixtures-heading">
        <p className="tt-kicker">05 / What&apos;s on</p>
        <h2 id="fixtures-heading" className="tt-display mt-1 text-4xl leading-none sm:text-5xl">Upcoming fixtures</h2>
        {upcomingFixtures.length === 0 ? <div className="mt-5 border-y-2 border-[var(--tt-ink)] py-6"><p className="tt-display text-3xl">Nothing scheduled yet.</p><p className="mt-2 text-[var(--tt-muted)]">There are no upcoming fixtures for this ground in Matchgoer.</p></div> : <><div className="mt-5 grid gap-3 sm:grid-cols-2">{featuredFixtures.map((fixture) => {
        const isInterested =
          interestedFixtureIds.includes(
            Number(fixture.fixture_id)
          );

        const fixtureDate =
          new Date(
            fixture.fixture_date
          );
        const statusGroup = fixtureStatusGroup(fixture.status);

        return (
          <article key={fixture.fixture_id} className="tt-panel flex min-w-0 flex-col overflow-hidden">
            <Link href={`/fixture/${fixture.fixture_id}`} className="min-w-0 flex-1 p-4 hover:text-[var(--tt-blue)] sm:p-5" aria-label={`${fixture.home_team} versus ${fixture.away_team}`}>
              <p className="tt-kicker">{fixture.league_name}</p>
              <FixtureTeams homeTeam={fixture.home_team} awayTeam={fixture.away_team} className="mt-3" teamClassName="text-[1.65rem] leading-[0.9]" separatorClassName="my-1 text-[0.65rem] tracking-[0.16em]" />
              <p className="mt-4 text-xs font-extrabold uppercase tracking-[0.08em]">{statusGroup === "postponed" || statusGroup === "cancelled" ? fixtureStatusLabel(fixture.status) : <>{fixtureDate.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })} · {fixtureDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</>}</p>
              <p className="mt-2 text-xs font-bold text-[var(--tt-muted)]">{fixture.interested_count} interested</p>
            </Link>
            <button
              type="button"
onClick={() => {
  if (updatingInterestedFixtureIds.includes(fixture.fixture_id)) return;
  setUpdatingInterestedFixtureIds((current) => [...current, fixture.fixture_id]);
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
      }).finally(() => setUpdatingInterestedFixtureIds((current) => current.filter((id) => id !== fixture.fixture_id)));

    return;
  }

  api
    .post(
      `/fixtures/${fixture.fixture_id}/interested`
    )
    .then((sessionResponse) => {
      const anonymous = sessionResponse.data.anonymous !== false;

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
      if (anonymous) setShowAccountPrompt(true);

    })
    .catch((error) => {
      console.error(
        "Add Interested error:",
        error
      );
    }).finally(() => setUpdatingInterestedFixtureIds((current) => current.filter((id) => id !== fixture.fixture_id)));
}}
              disabled={updatingInterestedFixtureIds.includes(fixture.fixture_id)}
              aria-pressed={isInterested}
              className={`tt-action rounded-none border-x-0 border-b-0 px-4 ${isInterested ? "bg-[var(--tt-blue)]" : "tt-action-secondary"}`}
            >
              {isInterested
                ? "✓ Interested"
                : "Interested"}
            </button>

          </article>
        );
      })}</div>{upcomingFixtures.length > 4 && <p className="mt-4 text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-muted)]">Showing the next 4 of {upcomingFixtures.length} upcoming fixtures.</p>}</>}
      </section>

    </main>
  );
}
