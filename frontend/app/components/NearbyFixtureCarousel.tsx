"use client";

import { formatKickoffTime, formatFixtureDistance } from "../../lib/fixture-format";

import Link from "next/link";

import { apiAssetUrl } from "../../lib/api";
import { fixtureStatusGroup, fixtureStatusLabel } from "../../lib/fixture-status";
import type { Fixture } from "../types/fixture";
import FixtureTeams from "./FixtureTeams";

type Props = {
  fixtures: Fixture[];
  showDistance: boolean;
  distanceOrigin?: string;
  totalMatches: number;
  resultsLimited: boolean;
  interestedFixtureIds: number[];
  updatingFixtureIds: number[];
  selectedFixtureId: number | null;
  onFixtureSelect: (fixtureId: number) => void;
  onToggleInterested: (fixtureId: number) => void;
};

export default function NearbyFixtureCarousel({ fixtures, showDistance, distanceOrigin, totalMatches, resultsLimited, interestedFixtureIds, updatingFixtureIds, selectedFixtureId, onFixtureSelect, onToggleInterested }: Props) {
  if (fixtures.length === 0) return null;

  return (
    <section aria-labelledby="nearby-fixtures-heading" className="mg-editorial-rule mt-3 min-w-0 pt-2 sm:mt-4 sm:pt-3">
      <div className="mb-2">
          <p className="mg-section-label">03 / Choose a match</p>
        <div className="flex items-center justify-between gap-3">
          <h2 id="nearby-fixtures-heading" className="mg-display-section mt-1">What&apos;s on</h2>
        <span className="shrink-0 bg-[var(--brand-interactive)] px-2.5 py-1.5 text-xs font-extrabold uppercase tracking-wider text-[var(--tt-paper)]">
          {resultsLimited ? `${fixtures.length} of ${totalMatches}` : totalMatches} {totalMatches === 1 ? "match" : "matches"}
        </span>
        </div>
        <p className="mt-1 text-[11px] leading-4 text-[var(--mg-muted)]">Earliest kick-off first · Times shown in your timezone</p>
      </div>

      <div className="grid min-w-0 items-start gap-2 md:grid-cols-2 xl:grid-cols-3" aria-label="Nearby fixtures">
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
              aria-current={isSelected ? "true" : undefined}
              className="@container group relative flex min-w-0 flex-col border border-[var(--tt-ink)] bg-[var(--tt-paper)] p-3"
            >
              <Link href={`/fixture/${fixture.fixture_id}`} className="block min-w-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]" aria-label={`${fixture.home_team} versus ${fixture.away_team} at ${fixture.venue_name}`}>
                <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                  <p className="text-xs font-extrabold uppercase tracking-[0.12em] text-[var(--brand-interactive)]">
                    {kickoff.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })} · {formatKickoffTime(kickoff)}
                  </p>
                  {hasResult ? <span className="bg-[var(--tt-ink)] px-2 py-1 text-sm font-extrabold text-[var(--tt-paper)]">{fixture.home_goals}–{fixture.away_goals}</span> : statusGroup === "postponed" || statusGroup === "cancelled" ? <span className="bg-[var(--tt-ink)] px-2 py-1 text-[0.62rem] font-extrabold uppercase tracking-wide text-[var(--tt-paper)]">{fixtureStatusLabel(fixture.status)}</span> : null}
                  {showMeaningfulDistance && <span className="min-w-0 break-words text-xs font-bold text-[var(--tt-muted)]">{formatFixtureDistance(fixture.distance_miles, distanceOrigin)}</span>}
                </div>

                <FixtureTeams
                  compact
                  homeTeam={fixture.home_team}
                  awayTeam={fixture.away_team}
                  homeBadgeSrc={apiAssetUrl(fixture.home_team_badge_url)}
                  awayBadgeSrc={apiAssetUrl(fixture.away_team_badge_url)}
                  teamClassName="text-[clamp(1.25rem,5cqw,1.5rem)] leading-[1.05]"
                  separatorClassName="text-[0.65rem]"
                  badgeClassName="h-12 w-12"
                />

                <div className="mt-2 grid min-w-0 gap-0.5 text-xs">
                  <p className="min-w-0 break-words font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)]">{fixture.league_name}</p>
                  <p className="min-w-0 break-words font-bold">{fixture.venue_name || fixture.venue_city || "Ground not available"}</p>
                </div>

                {highlighted && fixture.lead_decision_reason && <p className="mt-2 inline-flex items-center gap-1 border border-[var(--tt-gold)] px-2 py-1 text-[0.64rem] font-bold uppercase tracking-[0.06em]">
                  <span aria-hidden="true">{fixture.lead_decision_reason.emoji}</span>{fixture.lead_decision_reason.label}
                </p>}

                {fixture.away_day_score !== null && <p className="mt-1 text-[0.68rem] font-extrabold text-[var(--tt-muted)]">Ground rating {fixture.away_day_score.toFixed(1)}/10</p>}
              </Link>
              <div className={`mt-2 grid items-stretch gap-2 ${isInterested ? "grid-cols-1 @min-[340px]:grid-cols-[1fr_1.65fr]" : "grid-cols-2"}`}>
              <Link href={`/fixture/${fixture.fixture_id}`} className="flex min-h-11 items-center justify-center border border-[var(--brand-interactive)] bg-[var(--brand-interactive)] px-3 py-2 text-center text-xs font-extrabold uppercase tracking-[0.04em] text-[var(--tt-paper)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">View match →</Link>
              <button type="button" aria-label={isInterested ? `Remove ${fixture.home_team} versus ${fixture.away_team} from My Matchdays` : `Save ${fixture.home_team} versus ${fixture.away_team} to My Matchdays`} aria-pressed={isInterested} disabled={isUpdating} onClick={() => onToggleInterested(fixture.fixture_id)} className="min-h-11 min-w-0 border border-[var(--brand-interactive)] bg-[var(--tt-paper)] px-3 py-2 text-xs font-extrabold uppercase tracking-[0.04em] text-[var(--brand-interactive)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)] disabled:cursor-wait disabled:opacity-60">
                <span className="inline-flex items-center justify-center gap-2">
                  <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    {isInterested ? <path d="m5 12 4 4L19 6" /> : <path d="M6 3h12v18l-6-4-6 4z" />}
                  </svg>
                  {isInterested ? "Added to My Matchdays" : "Save match"}
                </span>
              </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
