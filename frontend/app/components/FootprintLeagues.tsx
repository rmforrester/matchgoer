"use client";

import Link from "next/link";
import GroundMatchdays from "./GroundMatchdays";
import type { FootprintSummary, MyGround } from "../types/grounds";
import { competitionsForGrounds, type FootprintPeriod } from "../../lib/football-footprint";

export default function FootprintLeagues({ grounds, footprint, period }: {
  grounds: MyGround[]; footprint: FootprintSummary | null; period: FootprintPeriod;
}) {
  const competitions = competitionsForGrounds(footprint?.competitions ?? [], grounds, period);
  const seasons = [...new Set(competitions.map(competition => competition.season_label))];
  const classified = new Set(competitions.flatMap(competition => competition.grounds.map(ground => ground.venue_id)));
  const otherGrounds = grounds.filter(ground => !classified.has(ground.venue_id));
  return <div className="py-2">
    {seasons.map(season => <details key={season} open className="border-b border-[var(--tt-rule)]">
      <summary className="tt-display min-h-11 cursor-pointer py-3 text-xl leading-none text-[var(--tt-ink)]">{season}</summary>
      <ul className="pb-2 pl-2">{competitions.filter(competition => competition.season_label === season).map(competition => {
        const count = period === "lifetime" ? competition.lifetime_clubs : competition.season_clubs;
        return <li key={`${competition.competition_id}-${competition.season}`}><details>
          <summary className="min-h-11 cursor-pointer py-3 text-sm marker:text-[var(--brand-interactive)]">
            <span className="inline-flex w-[calc(100%-1.25rem)] items-start justify-between gap-2 align-top">
              <span className="min-w-0 break-words font-bold">{competition.name}</span>
              <span className="shrink-0 text-right text-xs font-bold text-[var(--brand-interactive)]">{competition.coverage === "ready" && count !== null ? <>{count} / {competition.total_clubs}<span className="sr-only"> clubs covered across the league</span></> : <>Coverage<br/>incomplete</>}</span>
            </span>
          </summary>
          <ul className="space-y-3 border-l border-[var(--tt-rule)] pb-3 pl-3">{competition.grounds.map(item => {
            const ground = grounds.find(ground => ground.venue_id === item.venue_id)!;
            return <li key={item.venue_id} className="min-w-0 border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] p-3"><Link className="inline-flex min-h-11 items-center break-words text-sm font-bold text-[var(--brand-interactive)] underline" href={`/venue/${item.venue_id}`}>{ground.venue_name}</Link>
              <p className="pb-2 text-xs text-[var(--tt-muted)]">{item.clubs.length ? item.clubs.join(" · ") : "Home-ground coverage not verified"}</p><GroundMatchdays key={ground.visits.map(visit => visit.visit_id).join(",")} ground={ground} /></li>;
          })}</ul>
        </details></li>;
      })}</ul>
    </details>)}
    {otherGrounds.length > 0 && <div className="pt-3"><h4 className="tt-kicker text-xs">{competitions.length ? "Other grounds you've visited" : "Grounds you've visited"}</h4><ul className="mt-3 space-y-3">{otherGrounds.map(ground => <li key={ground.venue_id} className="min-w-0 border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] p-3"><Link href={`/venue/${ground.venue_id}`} className="inline-flex min-h-11 items-center break-words text-sm font-bold text-[var(--brand-interactive)] underline">{ground.venue_name}</Link><GroundMatchdays key={ground.visits.map(visit => visit.visit_id).join(",")} ground={ground} /></li>)}</ul></div>}
  </div>;
}
