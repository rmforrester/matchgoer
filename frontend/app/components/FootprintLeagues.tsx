"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import GroundMatchdays from "./GroundMatchdays";
import type { FootprintSummary, MyGround } from "../types/grounds";
import { competitionGroundProgress, competitionsForGrounds, type FootprintPeriod } from "../../lib/football-footprint";
import { formatMatchdayDate, matchdayDate } from "../../lib/ground-matchdays";

// Presentation state only; survives tab navigation without storing supporter data.
const expansion = new Map<string, boolean>();
export default function FootprintLeagues({ grounds, footprint, period, renderVisits, renderGroundActions }: {
  grounds: MyGround[]; footprint: FootprintSummary | null; period: FootprintPeriod; renderVisits?: (ground: MyGround, context: string) => ReactNode; renderGroundActions?: (ground: MyGround, context: string) => ReactNode;
}) {
  const [openings, setOpenings] = useState(() => new Map(expansion));
  const competitions = competitionsForGrounds(footprint?.attendance_competitions ?? footprint?.competitions ?? [], grounds, period);
  const seasons = [...new Set(competitions.map(competition => competition.season_label))];
  const classified = new Set(competitions.flatMap(competition => competition.grounds.map(ground => ground.venue_id)));
  const classifiedVisits = new Set(competitions.flatMap(competition => competition.grounds.flatMap(item => item.visit_ids ?? [])));
  const otherGrounds = grounds.flatMap(ground => {
    if (footprint?.attendance_competitions == null) return classified.has(ground.venue_id) ? [] : [ground];
    const visits = ground.visits.filter(visit => !classifiedVisits.has(visit.visit_id));
    if (!visits.length && (ground.visits.length || !ground.independently_saved)) return [];
    return [{ ...ground, visits, visit_count: visits.length }];
  });
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
      <button type="button" aria-expanded={openings.get(`${prefix}-ground-${context}`) ?? false} aria-controls={`${prefix}-visits-${context}`} onClick={() => { const id = `${prefix}-ground-${context}`; const next = !(openings.get(id) ?? false); expansion.set(id, next); setOpenings(previous => new Map(previous).set(id, next)); }} className="w-full text-left">
        <span className="flex min-h-11 items-center gap-3 py-3">
          <svg aria-hidden="true" data-ground-icon viewBox="0 0 24 24" className="h-8 w-8 shrink-0 text-[var(--brand-interactive)]" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 9v11h18V9L12 5 3 9Zm0 4 9 4 9-4M7 11v9m10-9v9M12 2v3M3 3v6m18-6v6"/></svg>
          <span className="min-w-0 flex-1"><span className="block break-words text-base font-bold text-[var(--brand-interactive)]">{ground.venue_name}</span>
            <span className="block text-xs text-[var(--tt-muted)]">{[ground.venue_city, ground.venue_country].filter(Boolean).join(" \u00b7 ")}</span>
            <span className="mt-1 block text-xs">{ground.visits.length} {ground.visits.length === 1 ? "matchday" : "matchdays"}<span className="text-[var(--tt-muted)]">{latest ? ` \u00b7 ${formatMatchdayDate(latest)}` : " \u00b7 DATE NOT RECORDED"}</span></span>
          </span><span aria-hidden="true" className={`text-lg text-[var(--brand-interactive)] ${openings.get(`${prefix}-ground-${context}`) ? "rotate-180" : ""}`}>{"\u2304"}</span>
        </span>
      </button>
      {renderGroundActions?.(ground, context)}
        {openings.get(`${prefix}-ground-${context}`) && <div id={`${prefix}-visits-${context}`} className="pb-3">{renderVisits?.(ground, context) ?? <GroundMatchdays ground={ground} />}<Link href={`/venue/${ground.venue_id}`} className="mt-2 inline-flex min-h-11 items-center text-xs font-bold text-[var(--brand-interactive)]">GROUND DETAILS {"\u2192"}</Link></div>}
    </li>;
  }
  return <div className="py-2">
    {seasons.map(season => <details key={season} {...disclosure(`season-${season}`, true)} className="border-b border-[var(--tt-rule)]">
      <summary className="tt-display min-h-11 cursor-pointer py-3 text-xl leading-none">{season}</summary>
      <ul className="pb-2">{competitions.filter(competition => competition.season_label === season).map(competition => {
        const progress = competitionGroundProgress(competition);
        return <li key={`${competition.competition_id}-${competition.season}`}><details {...disclosure(`league-${competition.competition_id}-${competition.season}`)}>
          <summary className="min-h-11 cursor-pointer py-3 text-sm marker:text-[var(--brand-interactive)]"><span className="inline-flex w-[calc(100%-1.25rem)] items-start justify-between gap-2 align-top"><span className="min-w-0 break-words font-bold">{competition.name}</span>{progress && <span className="shrink-0 text-right text-xs font-bold text-[var(--brand-interactive)]">{progress}</span>}</span></summary>
          <ul className="pl-2">{competition.grounds.map(item => { const ground = grounds.find(ground => ground.venue_id === item.venue_id)!; const visits = item.visit_ids ? ground.visits.filter(visit => item.visit_ids!.includes(visit.visit_id)) : ground.visits; return card({ ...ground, visits, visit_count: visits.length }, `${competition.competition_id}-${competition.season}-${item.venue_id}`); })}</ul>
        </details></li>;
      })}</ul>
    </details>)}
    {otherGrounds.length > 0 && <details {...disclosure("other")} className="border-b border-[var(--tt-rule)]"><summary className="tt-kicker min-h-11 cursor-pointer py-3 text-xs">OTHER GROUNDS YOU&apos;VE VISITED ({otherGrounds.length})</summary><ul>{otherGrounds.map(ground => card(ground, `other-${ground.venue_id}`))}</ul></details>}
  </div>;
}
