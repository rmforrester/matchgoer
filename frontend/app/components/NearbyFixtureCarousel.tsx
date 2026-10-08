"use client";

import Link from "next/link";

import { apiAssetUrl } from "../../lib/api";
import { fixtureStatusGroup, fixtureStatusLabel } from "../../lib/fixture-status";
import type { Fixture } from "../types/fixture";
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
    <section aria-labelledby="nearby-fixtures-heading" className="mg-editorial-rule mt-4 min-w-0 pt-3 sm:mt-6 sm:pt-4">
      <div className="mb-3 flex items-end justify-between gap-4">
        <div>
          <p className="mg-section-label">03 / Choose a match</p>
          <h2 id="nearby-fixtures-heading" className="mg-display-section mt-1">What&apos;s on</h2>
          <p className="mg-meta mt-1 text-xs font-bold uppercase tracking-[0.1em]">Earliest kick-off first</p>
        </div>
        <span className="shrink-0 bg-[var(--brand-interactive)] px-2.5 py-1.5 text-xs font-extrabold uppercase tracking-wider text-[var(--tt-paper)]">
          {resultsLimited ? `${fixtures.length} of ${totalMatches}` : totalMatches} {totalMatches === 1 ? "match" : "matches"}
        </span>
      </div>

      <div className="grid min-w-0 gap-x-6 md:grid-cols-2 xl:grid-cols-3" aria-label="Nearby fixtures">
        {fixtures.map((fixture) => {
          const kickoff = new Date(fixture.fixture_date);
          const statusGroup = fixtureStatusGroup(fixture.status);
          const hasResult = statusGroup === "finished" && fixture.home_goals !== null && fixture.away_goals !== null;
          const isInterested = interestedFixtureIds.includes(fixture.fixture_id);
          const isUpdating = updatingFixtureIds.includes(fixture.fixture_id);
          const isSelected = selectedFixtureId === fixture.fixture_id;
          const showMeaningfulDistance = showDistance && Number.isFinite(fixture.distance_miles);
          const highlighted = fixture.highlight_eligible && fixture.lead_decision_reason !== null;

          return (
            <article
              key={fixture.fixture_id}
              onFocus={() => onFixtureSelect(fixture.fixture_id)}
              onPointerEnter={() => onFixtureSelect(fixture.fixture_id)}
              className={`group relative min-w-0 border-t bg-transparent py-4 transition first:border-t-0 md:first:border-t ${highlighted ? "border-[var(--tt-gold)]" : "border-[var(--tt-rule)]"} ${isSelected ? "-translate-y-0.5 bg-[var(--tt-paper)] shadow-[3px_3px_0_var(--tt-rule)]" : ""}`}
            >
              <Link href={`/fixture/${fixture.fixture_id}`} className={`block min-w-0 px-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)] ${highlighted ? "border-l-[6px] border-[var(--tt-gold)] pl-3" : ""}`} aria-label={`${fixture.home_team} versus ${fixture.away_team} at ${fixture.venue_name}`}>
                <div className="mb-3 flex items-start justify-between gap-3">
                  <p className="text-xs font-extrabold uppercase tracking-[0.12em] text-[var(--brand-interactive)]">
                    {kickoff.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })} · {kickoff.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                  </p>
                  {hasResult ? <span className="bg-[var(--tt-ink)] px-2 py-1 text-sm font-extrabold text-[var(--tt-paper)]">{fixture.home_goals}–{fixture.away_goals}</span> : statusGroup === "postponed" || statusGroup === "cancelled" ? <span className="bg-[var(--tt-ink)] px-2 py-1 text-[0.62rem] font-extrabold uppercase tracking-wide text-[var(--tt-paper)]">{fixtureStatusLabel(fixture.status)}</span> : null}
                  {showMeaningfulDistance && <span className="shrink-0 text-xs font-bold text-[var(--tt-muted)]">{fixture.distance_miles.toFixed(1)} mi</span>}
                </div>

                <FixtureTeams
                  staggered
                  homeTeam={fixture.home_team}
                  awayTeam={fixture.away_team}
                  homeBadgeSrc={apiAssetUrl(fixture.home_team_badge_url)}
                  awayBadgeSrc={apiAssetUrl(fixture.away_team_badge_url)}
                  teamClassName="text-[1.4rem] leading-[1.05] sm:text-[1.6rem]"
                  separatorClassName="text-[0.65rem]"
                  badgeClassName="h-12 w-12 sm:h-14 sm:w-14"
                />

                <div className="mt-3 grid min-w-0 gap-1 text-xs">
                  <p className="min-w-0 break-words font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)]">{fixture.league_name}</p>
                  <p className="min-w-0 break-words font-bold">{fixture.venue_name || fixture.venue_city || "Ground not available"}</p>
                </div>

                {highlighted && fixture.lead_decision_reason && <p className="mt-3 inline-flex items-center gap-1 border border-[var(--tt-gold)] px-2 py-1 text-[0.64rem] font-bold uppercase tracking-[0.06em]">
                  <span aria-hidden="true">{fixture.lead_decision_reason.emoji}</span>{fixture.lead_decision_reason.label}
                </p>}

                <div className="mt-4 flex items-center justify-between gap-3 border-t border-[var(--tt-rule)] pt-3">
                  <span className="font-extrabold uppercase tracking-[0.1em] text-[var(--brand-interactive)]">View match →</span>
                  {fixture.away_day_score !== null && <span className="text-[0.68rem] font-extrabold text-[var(--tt-muted)]">Ground rating {fixture.away_day_score.toFixed(1)}/10</span>}
                </div>
              </Link>

              <button type="button" aria-label={isInterested ? `Remove ${fixture.home_team} versus ${fixture.away_team} from My Matchdays` : `Save ${fixture.home_team} versus ${fixture.away_team} to My Matchdays`} aria-pressed={isInterested} disabled={isUpdating} onClick={() => onToggleInterested(fixture.fixture_id)} className={`mt-2 min-h-11 w-full px-3 text-xs font-extrabold uppercase tracking-[0.1em] transition disabled:cursor-wait disabled:opacity-60 ${isInterested ? "bg-[var(--tt-newsprint)] text-[var(--brand-interactive)]" : "text-[var(--tt-muted)] underline decoration-2 underline-offset-4 hover:text-[var(--brand-interactive)]"}`}>
                <span className="inline-flex items-center justify-center gap-2">
                  <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    {isInterested ? <path d="m5 12 4 4L19 6" /> : <path d="M6 3h12v18l-6-4-6 4z" />}
                  </svg>
                  {isInterested ? "Added to My Matchdays" : "Save match"}
                </span>
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}
