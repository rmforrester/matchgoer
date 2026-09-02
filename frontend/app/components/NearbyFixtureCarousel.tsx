"use client";

import Link from "next/link";

import type { Fixture } from "../types/fixture";
import { fixtureStatusGroup, fixtureStatusLabel } from "../../lib/fixture-status";
import FixtureTeams from "./FixtureTeams";

type Props = {
  fixtures: Fixture[];
  showDistance: boolean;
  totalMatches: number;
  resultsLimited: boolean;
  interestedFixtureIds: number[];
  updatingFixtureIds: number[];
  selectedFixtureId: number | null;
  onFixtureSelect: (fixtureId: number) => void;
  onToggleInterested: (fixtureId: number) => void;
};

export default function NearbyFixtureCarousel({ fixtures, showDistance, totalMatches, resultsLimited, interestedFixtureIds, updatingFixtureIds, selectedFixtureId, onFixtureSelect, onToggleInterested }: Props) {
  if (fixtures.length === 0) return null;

  return (
    <section aria-labelledby="nearby-fixtures-heading" className="tt-section-rule mt-3 min-w-0 pt-3">
      <div className="mb-2 flex items-end justify-between gap-3">
        <div>
          <p className="tt-kicker">03 / Choose a match</p>
          <h2 id="nearby-fixtures-heading" className="tt-display mt-1 text-3xl leading-none sm:text-4xl">What&apos;s on</h2>
          <p className="mt-1 text-xs font-bold uppercase tracking-wide text-[var(--tt-muted)]">Earliest kickoff first</p>
        </div>
        <span className="shrink-0 bg-[var(--tt-blue)] px-2 py-1 text-xs font-extrabold uppercase tracking-wider text-[var(--tt-paper)]">
          {resultsLimited ? `${fixtures.length} of ${totalMatches}` : totalMatches} {totalMatches === 1 ? "match" : "matches"}
        </span>
      </div>

      <div className="tt-scrollbar flex max-w-full snap-x snap-mandatory gap-3 overflow-x-auto overscroll-x-contain pb-4 [-webkit-overflow-scrolling:touch]" aria-label="Nearby fixtures, scroll horizontally">
        {fixtures.map((fixture) => {
          const kickoff = new Date(fixture.fixture_date);
          const statusGroup = fixtureStatusGroup(fixture.status);
          const hasResult = statusGroup === "finished" && fixture.home_goals !== null && fixture.away_goals !== null;
          const isInterested = interestedFixtureIds.includes(fixture.fixture_id);
          const isUpdating = updatingFixtureIds.includes(fixture.fixture_id);
          const isSelected = selectedFixtureId === fixture.fixture_id;
          const showMeaningfulDistance = showDistance && Number.isFinite(fixture.distance_miles);

          return (
            <article
              key={fixture.fixture_id}
              onFocus={() => onFixtureSelect(fixture.fixture_id)}
              onPointerEnter={() => onFixtureSelect(fixture.fixture_id)}
              className={`group relative flex h-[18.5rem] w-[72vw] min-w-[14.5rem] max-w-[16rem] snap-start flex-col border-2 bg-[var(--tt-paper)] text-[var(--tt-ink)] transition sm:w-64 ${isSelected ? "-translate-y-0.5 border-[var(--tt-blue)] shadow-[3px_3px_0_var(--tt-blue)]" : "border-[var(--tt-ink)] hover:-translate-y-0.5 hover:border-[var(--tt-blue)]"}`}
            >
              <Link href={`/fixture/${fixture.fixture_id}`} className="flex min-h-0 flex-1 flex-col overflow-hidden p-3 focus-visible:outline-2 focus-visible:outline-offset-[-4px] focus-visible:outline-[var(--tt-blue)]" aria-label={`${fixture.home_team} versus ${fixture.away_team} at ${fixture.venue_name}`}>
                <div className="mb-2 flex items-start justify-between gap-3 border-b-2 border-[var(--tt-ink)] pb-2">
                  <div className="flex items-end gap-2">
                    <span className="tt-display text-3xl leading-[0.8] text-[var(--tt-blue)]">{kickoff.toLocaleDateString(undefined, { day: "2-digit" })}</span>
                    <p className="text-[0.62rem] font-extrabold uppercase leading-tight tracking-[0.12em]">{kickoff.toLocaleDateString(undefined, { weekday: "short" })}<br />{kickoff.toLocaleDateString(undefined, { month: "short" })}</p>
                  </div>
                  {hasResult ? <span className="bg-[var(--tt-ink)] px-2 py-1 text-sm font-extrabold text-[var(--tt-paper)]">{fixture.home_goals}–{fixture.away_goals}</span> : statusGroup === "postponed" || statusGroup === "cancelled" ? <span className="bg-[var(--tt-ink)] px-2 py-1 text-[0.62rem] font-extrabold uppercase tracking-wide text-[var(--tt-paper)]">{fixtureStatusLabel(fixture.status)}</span> : <span className="text-sm font-extrabold tabular-nums">{kickoff.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</span>}
                </div>

                <div className="h-[5.15rem] shrink-0 overflow-hidden">
                  <FixtureTeams homeTeam={fixture.home_team} awayTeam={fixture.away_team} teamClassName="line-clamp-2 text-[1.28rem] leading-[0.92]" separatorClassName="my-0.5 text-[0.62rem]" />
                </div>
                <p className="mt-2 truncate text-[0.66rem] font-extrabold uppercase tracking-[0.1em] text-[var(--tt-blue)]">{fixture.league_name}</p>

                <div className="mt-auto border-t border-[var(--tt-rule)] pt-2 text-[0.68rem]">
                  <p className="truncate font-extrabold uppercase tracking-[0.08em]">{fixture.venue_name}</p>
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <span className="font-bold text-[var(--tt-muted)]">{showMeaningfulDistance ? `${fixture.distance_miles.toFixed(1)} mi away` : ""}</span>
                    {fixture.away_day_score !== null && <span className="font-extrabold text-[var(--tt-blue)]">★ {fixture.away_day_score.toFixed(1)}</span>}
                  </div>
                  <span className="mt-2 inline-block font-extrabold uppercase tracking-[0.1em] text-[var(--tt-blue)]">View match →</span>
                </div>
              </Link>

              <button type="button" aria-label={isInterested ? `Remove ${fixture.home_team} versus ${fixture.away_team} from Interested` : `Save ${fixture.home_team} versus ${fixture.away_team} as Interested`} aria-pressed={isInterested} disabled={isUpdating} onClick={() => onToggleInterested(fixture.fixture_id)} className={`flex min-h-11 items-center justify-center border-t border-[var(--tt-ink)] px-3 text-[0.66rem] font-extrabold uppercase tracking-[0.12em] transition disabled:cursor-wait disabled:opacity-60 ${isInterested ? "bg-[var(--tt-blue)] text-[var(--tt-paper)]" : "bg-[var(--tt-paper)] text-[var(--tt-muted)] hover:bg-[var(--tt-ink)] hover:text-[var(--tt-paper)]"}`}>
                {isInterested ? "✓ Interested" : "Interested"}
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}
