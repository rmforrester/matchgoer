import Link from "next/link";

import type { Fixture } from "../types/fixture";
import { fixtureStatusGroup, fixtureStatusLabel } from "../../lib/fixture-status";
import FixtureTeams from "./FixtureTeams";

type Props = {
  fixtures: Fixture[];
  radius: number;
  viewportMode: boolean;
  totalMatches: number;
  resultsLimited: boolean;
  interestedFixtureIds: number[];
  updatingFixtureIds: number[];
  onToggleInterested: (fixtureId: number) => void;
};

export default function NearbyFixtureCarousel({
  fixtures,
  radius,
  viewportMode,
  totalMatches,
  resultsLimited,
  interestedFixtureIds,
  updatingFixtureIds,
  onToggleInterested,
}: Props) {
  if (fixtures.length === 0) return null;

  return (
    <section aria-labelledby="nearby-fixtures-heading" className="tt-section-rule mt-8 min-w-0 pt-4">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <p className="tt-kicker">03 / Fixture list</p>
          <h2 id="nearby-fixtures-heading" className="tt-display mt-1 text-3xl leading-none sm:text-4xl">
            What&apos;s on
          </h2>
          <p className="mt-1 text-sm text-[var(--tt-muted)]">
            {viewportMode ? "Matches in this area" : `Within ${radius} miles`} · earliest kickoff first
          </p>
        </div>
        <span className="shrink-0 bg-[var(--tt-blue)] px-2 py-1 text-xs font-extrabold uppercase tracking-wider text-[var(--tt-paper)]">
          {resultsLimited ? `${fixtures.length} of ${totalMatches}` : totalMatches} {totalMatches === 1 ? "match" : "matches"} →
        </span>
      </div>

      <div
        className="tt-scrollbar flex max-w-full snap-x snap-mandatory gap-4 overflow-x-auto overscroll-x-contain pb-5 [-webkit-overflow-scrolling:touch]"
        aria-label="Nearby fixtures, scroll horizontally"
      >
        {fixtures.map((fixture) => {
          const kickoff = new Date(fixture.fixture_date);
          const statusGroup = fixtureStatusGroup(fixture.status);
          const hasResult = statusGroup === "finished"
            && fixture.home_goals !== null
            && fixture.away_goals !== null;
          const isInterested = interestedFixtureIds.includes(fixture.fixture_id);
          const isUpdating = updatingFixtureIds.includes(fixture.fixture_id);

          return (
            <article
              key={fixture.fixture_id}
              className="group relative aspect-square w-[78vw] max-w-[18rem] min-w-[16rem] snap-start overflow-hidden border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] text-[var(--tt-ink)] transition hover:-translate-y-0.5 hover:border-[var(--tt-blue)] sm:w-72"
            >
              <Link
                href={`/fixture/${fixture.fixture_id}`}
                className="flex h-full flex-col justify-between p-4 pb-16 focus-visible:outline-2 focus-visible:outline-offset-[-4px] focus-visible:outline-[var(--tt-blue)]"
                aria-label={`${fixture.home_team} versus ${fixture.away_team} at ${fixture.venue_name}`}
              >
                <div className="min-w-0">
                  <div className="mb-3 flex items-start justify-between gap-3 border-b-2 border-[var(--tt-ink)] pb-3">
                    <div className="flex items-end gap-2">
                      <span className="tt-display text-4xl leading-[0.8] text-[var(--tt-blue)]">
                        {kickoff.toLocaleDateString(undefined, { day: "2-digit" })}
                      </span>
                      <p className="text-[0.68rem] font-extrabold uppercase leading-tight tracking-[0.12em]">
                        {kickoff.toLocaleDateString(undefined, { weekday: "long" })}<br />
                        {kickoff.toLocaleDateString(undefined, { month: "short" })}
                      </p>
                    </div>
                    {hasResult && (
                      <span className="bg-[var(--tt-ink)] px-2 py-1 text-sm font-extrabold text-[var(--tt-paper)]">
                        {fixture.home_goals}–{fixture.away_goals}
                      </span>
                    )}
                    {!hasResult && statusGroup !== "postponed" && statusGroup !== "cancelled" && (
                      <span className="text-sm font-extrabold tabular-nums">
                        {kickoff.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    )}
                    {(statusGroup === "postponed" || statusGroup === "cancelled") && (
                      <span className="bg-[var(--tt-ink)] px-2 py-1 text-[0.65rem] font-extrabold uppercase tracking-wide text-[var(--tt-paper)]">
                        {fixtureStatusLabel(fixture.status)}
                      </span>
                    )}
                  </div>

                  <FixtureTeams
                    homeTeam={fixture.home_team}
                    awayTeam={fixture.away_team}
                    teamClassName="line-clamp-2 text-[1.5rem] leading-[0.9]"
                    separatorClassName="my-1 text-xs"
                  />
                  {fixture.open_to_meet_count > 0 && (
                    <p className="mt-2 text-xs font-extrabold uppercase tracking-wide text-[var(--tt-blue)]">
                      Who&apos;s Going? · {fixture.open_to_meet_count}
                    </p>
                  )}
                </div>

                <div className="min-w-0 border-t border-[var(--tt-rule)] pt-2 text-[0.7rem]">
                  <p className="truncate font-extrabold uppercase tracking-[0.08em]">{fixture.venue_name}</p>
                  <p className="truncate text-[var(--tt-muted)]">{fixture.venue_city || "Location unavailable"}</p>
                  <div className="mt-1.5 flex items-center justify-between gap-2 text-[0.68rem] uppercase tracking-wide">
                    <span className="font-bold text-[var(--tt-muted)]">
                      {fixture.distance_miles.toFixed(1)} mi away
                    </span>
                    <span className="min-w-0 text-right font-extrabold text-[var(--tt-blue)]">
                      {fixture.away_day_score !== null ? `★ ${fixture.away_day_score.toFixed(1)} rating` : "Unrated"}
                    </span>
                  </div>
                </div>
              </Link>

              <button
                type="button"
                aria-label={isInterested
                  ? `Remove ${fixture.home_team} versus ${fixture.away_team} from Interested`
                  : `Save ${fixture.home_team} versus ${fixture.away_team} as Interested`}
                aria-pressed={isInterested}
                disabled={isUpdating}
                onClick={() => onToggleInterested(fixture.fixture_id)}
                className={`absolute inset-x-0 bottom-0 z-10 flex min-h-11 items-center justify-center border-t-2 border-[var(--tt-ink)] px-4 text-[0.7rem] font-extrabold uppercase tracking-[0.12em] transition focus-visible:outline-2 focus-visible:outline-offset-[-4px] focus-visible:outline-[var(--tt-blue)] disabled:cursor-wait disabled:opacity-60 ${isInterested ? "bg-[var(--tt-blue)] text-[var(--tt-paper)]" : "bg-[var(--tt-paper)] text-[var(--tt-ink)] hover:bg-[var(--tt-blue)] hover:text-[var(--tt-paper)]"}`}
              >
                <span>{isInterested ? "✓ Interested" : "Interested"}</span>
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}
