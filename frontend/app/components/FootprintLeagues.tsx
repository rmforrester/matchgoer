"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import GroundMatchdays from "./GroundMatchdays";
import type { FootprintSummary, MyGround } from "../types/grounds";
import { competitionsForGrounds, type FootprintPeriod } from "../../lib/football-footprint";
import { formatMatchdayDate, matchdayDate } from "../../lib/ground-matchdays";

// Presentation state only; survives tab navigation without storing supporter data.
const expansion = new Map<string, boolean>();
export default function FootprintLeagues({ grounds, footprint, period, renderVisits }: {
  grounds: MyGround[]; footprint: FootprintSummary | null; period: FootprintPeriod; renderVisits?: (ground: MyGround, context: string) => ReactNode;
}) {
  const [openings, setOpenings] = useState(() => new Map(expansion));
  const competitions = competitionsForGrounds(footprint?.competitions ?? [], grounds, period);
  const seasons = [...new Set(competitions.map(competition => competition.season_label))];
  const classified = new Set(competitions.flatMap(competition => competition.grounds.map(ground => ground.venue_id)));
  const otherGrounds = grounds.filter(ground => !classified.has(ground.venue_id));
  const prefix = `${grounds[0]?.venue_country ?? "unknown"}-${period}`;
  function disclosure(key: string, initial = false) {
    const id = `${prefix}-${key}`;
    return { open: openings.get(id) ?? initial,
      onClick: (event: React.MouseEvent<HTMLDetailsElement>) => {
        if ((event.target as HTMLElement).closest("summary") !== event.currentTarget.firstElementChild) return;
        event.preventDefault();
        const next = !event.currentTarget.open;
        expansion.set(id, next); setOpenings(previous => new Map(previous).set(id, next));
      } };
  }
  function card(ground: MyGround, context: string) {
    const latest = ground.visits.map(visit => matchdayDate(visit.visit_date)).filter((date): date is string => date !== null).sort().at(-1);
    return <li key={ground.venue_id} className="min-w-0 border-b border-[var(--tt-rule)] last:border-0">
      <details {...disclosure(`ground-${context}`)}>
        <summary className="flex min-h-11 cursor-pointer list-none items-center gap-3 py-3 [&::-webkit-details-marker]:hidden group">
          <svg aria-hidden="true" data-ground-icon viewBox="0 0 24 24" className="h-8 w-8 shrink-0 text-[var(--brand-interactive)]" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 9v11h18V9L12 5 3 9Zm0 4 9 4 9-4M7 11v9m10-9v9M12 2v3M3 3v6m18-6v6"/></svg>
          <span className="min-w-0 flex-1"><span className="block break-words text-base font-bold text-[var(--brand-interactive)]">{ground.venue_name}</span>
            <span className="block text-xs text-[var(--tt-muted)]">{[ground.venue_city, ground.venue_country].filter(Boolean).join(" \u00b7 ")}</span>
            <span className="mt-1 block text-xs">{ground.visits.length} {ground.visits.length === 1 ? "matchday" : "matchdays"}<span className="text-[var(--tt-muted)]">{latest ? ` \u00b7 ${formatMatchdayDate(latest)}` : " \u00b7 DATE NOT RECORDED"}</span></span>
          </span><span aria-hidden="true" className="text-lg text-[var(--brand-interactive)] group-open:rotate-180">{"\u2304"}</span>
        </summary>
        {openings.get(`${prefix}-ground-${context}`) && <div className="pb-3">{renderVisits?.(ground, context) ?? <GroundMatchdays ground={ground} />}<Link href={`/venue/${ground.venue_id}`} className="mt-2 inline-flex min-h-11 items-center text-xs font-bold text-[var(--brand-interactive)]">GROUND DETAILS {"\u2192"}</Link></div>}
      </details>
    </li>;
  }
  return <div className="py-2">
    {seasons.map(season => <details key={season} {...disclosure(`season-${season}`, true)} className="border-b border-[var(--tt-rule)]">
      <summary className="tt-display min-h-11 cursor-pointer py-3 text-xl leading-none">{season}</summary>
      <ul className="pb-2">{competitions.filter(competition => competition.season_label === season).map(competition => {
        const count = period === "lifetime" ? competition.lifetime_clubs : competition.season_clubs;
        return <li key={`${competition.competition_id}-${competition.season}`}><details {...disclosure(`league-${competition.competition_id}-${competition.season}`)}>
          <summary className="min-h-11 cursor-pointer py-3 text-sm marker:text-[var(--brand-interactive)]"><span className="inline-flex w-[calc(100%-1.25rem)] items-start justify-between gap-2 align-top"><span className="min-w-0 break-words font-bold">{competition.name}</span><span className="shrink-0 text-right text-xs font-bold text-[var(--brand-interactive)]">{competition.coverage === "ready" && count !== null ? <>{count} / {competition.total_clubs}<span className="sr-only"> clubs covered across the league</span></> : <>Coverage<br/>incomplete</>}</span></span></summary>
          <ul className="pl-2">{competition.grounds.map(item => card(grounds.find(ground => ground.venue_id === item.venue_id)!, `${competition.competition_id}-${competition.season}-${item.venue_id}`))}</ul>
        </details></li>;
      })}</ul>
    </details>)}
    {otherGrounds.length > 0 && <details {...disclosure("other")} className="border-b border-[var(--tt-rule)]"><summary className="tt-kicker min-h-11 cursor-pointer py-3 text-xs">OTHER GROUNDS YOU&apos;VE VISITED ({otherGrounds.length})</summary><ul>{otherGrounds.map(ground => card(ground, `other-${ground.venue_id}`))}</ul></details>}
  </div>;
}
