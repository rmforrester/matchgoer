"use client";

import Link from "next/link";

import type { InterestedFixture } from "../types/interested";

export default function DiscoverShortlist({ fixtures, updatingFixtureIds, onRemove }: {
  fixtures: InterestedFixture[];
  updatingFixtureIds: number[];
  onRemove: (fixtureId: number) => void;
}) {
  if (fixtures.length === 0) return null;

  return <section className="tt-section-rule mt-8 pt-4" aria-labelledby="shortlist-heading">
    <p className="tt-kicker">Your shortlist</p>
    <h2 id="shortlist-heading" className="tt-display mt-1 text-3xl leading-none sm:text-4xl">Matches you&apos;re considering.</h2>
    <div className="mt-4 grid gap-3 md:grid-cols-2">
      {fixtures.map((fixture) => {
        const kickoff = new Date(fixture.fixture_date);
        const updating = updatingFixtureIds.includes(fixture.fixture_id);
        return <article key={fixture.fixture_id} className="tt-panel min-w-0 p-4">
          <p className="text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)]">
            {kickoff.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })} · {kickoff.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </p>
          <p className="mt-2 line-clamp-2 text-lg font-extrabold leading-tight">{fixture.home_team} <span className="text-[var(--tt-muted)]">v</span> {fixture.away_team}</p>
          <p className="mt-2 truncate text-xs font-bold uppercase tracking-[0.06em]">{fixture.venue_name ?? "Ground to be confirmed"}{fixture.venue_city ? ` · ${fixture.venue_city}` : ""}</p>
          <div className="mt-3 flex items-center gap-5 border-t border-[var(--tt-rule)] pt-3 text-xs font-extrabold uppercase tracking-[0.08em]">
            <Link href={`/fixture/${fixture.fixture_id}`} className="min-h-11 content-center text-[var(--tt-blue)] underline decoration-2 underline-offset-4">View match →</Link>
            <button type="button" disabled={updating} onClick={() => onRemove(fixture.fixture_id)} className="min-h-11 text-[var(--tt-muted)] underline decoration-2 underline-offset-4 disabled:opacity-60">{updating ? "Removing…" : "Remove"}</button>
          </div>
        </article>;
      })}
    </div>
  </section>;
}
