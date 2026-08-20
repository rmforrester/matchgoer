import Link from "next/link";

import type { Fixture } from "../types/fixture";
import { buildWorthTheTripRecommendations } from "../../lib/worthTheTrip";
import FixtureTeams from "./FixtureTeams";

type Props = {
  fixtures: Fixture[];
};

export default function WorthTheTrip({ fixtures }: Props) {
  const recommendations = buildWorthTheTripRecommendations(fixtures);

  return (
    <section aria-labelledby="worth-the-trip-heading" className="tt-section-rule mt-8 pt-4">
      <p className="tt-kicker">04 / Worth the trip</p>
      <h2 id="worth-the-trip-heading" className="tt-display mb-6 mt-2 max-w-3xl text-4xl leading-[0.9] sm:text-6xl">
        Don&apos;t just find a game.<br />
        <span className="text-[var(--tt-blue)]">Find one worth going to.</span>
      </h2>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {recommendations.map(({
          title,
          fixture,
          metric,
          emptyMessage,
          showOverallRating,
        }, index) => {
          const distanceLabel = fixture ? `${fixture.distance_miles.toFixed(1)} mi away` : null;
          const recommendationHeadline = title.replace(/^[^\p{L}\p{N}]+/u, "");
          const metricDuplicatesDistance = metric === distanceLabel;
          const showMetricRecommendation = Boolean(
            metric?.startsWith("🎟️")
            && fixture?.away_day_score !== null
            && fixture?.recommend_percentage !== null
          );

          return (
            <article
              key={title}
              className={`flex min-w-0 flex-col border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] text-[var(--tt-ink)] ${fixture ? "min-h-64 p-4" : "p-3.5"}`}
            >
              <p className="tt-kicker">0{index + 1} / Recommendation</p>
              <h3 className={`tt-display mt-1 border-b-2 border-[var(--tt-ink)] text-3xl leading-none text-[var(--tt-blue)] sm:text-4xl ${fixture ? "mb-3 pb-2.5" : "mb-2 pb-2"}`}>
                {recommendationHeadline}
              </h3>

              {!fixture ? (
                <p className="text-sm text-[var(--tt-muted)]">{emptyMessage}</p>
              ) : (
                <Link
                  href={`/fixture/${fixture.fixture_id}`}
                  className="flex flex-1 flex-col focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--tt-blue)]"
                >
                  <FixtureTeams
                    homeTeam={fixture.home_team}
                    awayTeam={fixture.away_team}
                    teamClassName="text-2xl leading-[0.95] sm:text-[1.65rem]"
                    separatorClassName="my-1.5 text-xs tracking-[0.12em]"
                  />

                  <p className="mt-3 truncate border-t border-[var(--tt-rule)] pt-2.5 text-sm font-extrabold uppercase tracking-wide">
                    {fixture.venue_name}
                  </p>

                  <p className="mt-2 text-sm text-[var(--tt-muted)]">
                    {new Date(fixture.fixture_date).toLocaleDateString(undefined, {
                      weekday: "short",
                      day: "numeric",
                      month: "short",
                    })}{" "}
                    ·{" "}
                    {new Date(fixture.fixture_date).toLocaleTimeString(undefined, {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>

                  <div className="mt-auto flex flex-wrap items-center gap-2 border-t border-[var(--tt-rule)] pt-3 text-xs font-extrabold uppercase">
                    {distanceLabel && (
                      <span className="border border-[var(--tt-ink)] px-2.5 py-1">{distanceLabel}</span>
                    )}
                    {metric && !metricDuplicatesDistance && (
                      <span className="border border-[var(--tt-ink)] px-2.5 py-1 text-[var(--tt-blue)]">{metric}</span>
                    )}
                    {showMetricRecommendation && fixture.recommend_percentage !== null && (
                      <span className="border border-[var(--tt-ink)] px-2.5 py-1 text-[var(--tt-blue)]">
                        👍 {Math.round(fixture.recommend_percentage)}% recommended
                      </span>
                    )}
                    {showOverallRating && fixture.away_day_score !== null && (
                      <span className="border border-[var(--tt-ink)] px-2.5 py-1 text-[var(--tt-blue)]">
                        🎟️ {fixture.away_day_score.toFixed(1)} Terrace Rating
                      </span>
                    )}
                    {showOverallRating && fixture.away_day_score !== null && fixture.recommend_percentage !== null && (
                      <span className="border border-[var(--tt-ink)] px-2.5 py-1 text-[var(--tt-blue)]">
                        👍 {Math.round(fixture.recommend_percentage)}% recommended
                      </span>
                    )}
                  </div>
                </Link>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
