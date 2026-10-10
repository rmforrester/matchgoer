"use client";

import { formatKickoffTime } from "../../lib/fixture-format";

import Link from "next/link";
import { apiAssetUrl } from "../../lib/api";
import type { Fixture } from "../types/fixture";
import FixtureTeams from "./FixtureTeams";

import type { InterestedFixture } from "../types/interested";

export default function DiscoverShortlist({ fixtures, discoveredFixtures, updatingFixtureIds, onRemove }: {
  fixtures: InterestedFixture[];
  discoveredFixtures: Fixture[];
  updatingFixtureIds: number[];
  onRemove: (fixtureId: number) => void;
}) {
  if (fixtures.length === 0) return null;

  return <section className="tt-section-rule mt-8 pt-4" aria-labelledby="shortlist-heading">
    <p className="tt-kicker">Your shortlist</p>
    <h2 id="shortlist-heading" className="tt-display mt-1 text-3xl leading-none sm:text-4xl">Matches you&apos;re considering.</h2>
    <div className="mt-4 grid min-w-0 items-start gap-2 md:grid-cols-2 xl:grid-cols-3">
      {fixtures.map((fixture) => {
        const kickoff = new Date(fixture.fixture_date);
        const updating = updatingFixtureIds.includes(fixture.fixture_id);
        const competition = discoveredFixtures.find((item) => item.fixture_id === fixture.fixture_id)?.league_name;
        return <article key={fixture.fixture_id} className="@container flex min-w-0 flex-col border border-[var(--tt-ink)] bg-[var(--tt-paper)] p-3">
          <p className="text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)]">
            {kickoff.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })} · {formatKickoffTime(kickoff)}
          </p>
          <FixtureTeams
            compact
            className="mt-2"
            homeTeam={fixture.home_team}
            awayTeam={fixture.away_team}
            homeBadgeSrc={apiAssetUrl(fixture.home_team_badge_url)}
            awayBadgeSrc={apiAssetUrl(fixture.away_team_badge_url)}
            teamClassName="text-[clamp(1.25rem,5cqw,1.5rem)] leading-[1.05]"
            separatorClassName="text-[0.65rem]"
            badgeClassName="h-12 w-12"
          />
          <div className="mt-2 grid min-w-0 gap-0.5 text-xs">
            {competition && <p className="min-w-0 break-words font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)]">{competition}</p>}
            <p className="min-w-0 break-words font-bold">{fixture.venue_name || "Ground to be confirmed"}{fixture.venue_city ? ` · ${fixture.venue_city}` : ""}</p>
          </div>
          <div className="mt-2 grid grid-cols-2 items-stretch gap-2">
            <Link href={`/fixture/${fixture.fixture_id}`} className="flex min-h-11 items-center justify-center border border-[var(--brand-interactive)] bg-[var(--brand-interactive)] px-3 py-2 text-center text-xs font-extrabold uppercase tracking-[0.04em] text-[var(--tt-paper)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">View match →</Link>
            <button type="button" disabled={updating} onClick={() => onRemove(fixture.fixture_id)} className="min-h-11 min-w-0 border border-[var(--brand-interactive)] bg-[var(--tt-paper)] px-3 py-2 text-xs font-extrabold uppercase tracking-[0.04em] text-[var(--brand-interactive)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)] disabled:cursor-wait disabled:opacity-60">{updating ? "Removing…" : "Remove"}</button>
          </div>
        </article>;
      })}
    </div>
  </section>;
}
