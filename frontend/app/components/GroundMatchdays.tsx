"use client";

import Link from "next/link";
import { useState } from "react";
import type { MyGround } from "../types/grounds";
import { formatMatchdayDate, groundMatchdays } from "../../lib/ground-matchdays";

export default function GroundMatchdays({ ground }: { ground: MyGround }) {
  const matchdays = groundMatchdays(ground);
  const [limit, setLimit] = useState(5);
  const [expanded, setExpanded] = useState(false);
  if (!matchdays.length) return null;
  function row(matchday: typeof matchdays[number]) {
    return <li key={matchday.visitId} className="py-1 text-xs">
      {matchday.title && <p className="break-words font-bold">{matchday.title}{matchday.result && <span> · {matchday.result}</span>}</p>}
      <p className="text-[var(--tt-muted)]">{formatMatchdayDate(matchday.date)}</p>
      <Link href={matchday.href} className="inline-flex min-h-11 items-center font-bold text-[var(--brand-interactive)] underline" aria-label={`${matchday.fixtureLinked ? "View matchday" : "View ground"}: ${matchday.title ?? ground.venue_name}, ${formatMatchdayDate(matchday.date)}`}>
        {matchday.fixtureLinked ? "VIEW MATCHDAY →" : "VIEW GROUND →"}
      </Link>
    </li>;
  }
  return <div className="pb-2">
    <h5 className="tt-kicker text-[10px]">YOUR MATCHDAYS</h5>
    <ul>{row(matchdays[0])}</ul>
    {matchdays.length > 1 && <details onToggle={event => { setExpanded(event.currentTarget.open); if (!event.currentTarget.open) setLimit(5); }}>
      <summary className="min-h-11 cursor-pointer py-3 text-xs font-bold text-[var(--brand-interactive)]">{expanded ? "HIDE ADDITIONAL MATCHDAYS ↑" : `SHOW ${matchdays.length - 1} MORE ${matchdays.length === 2 ? "MATCHDAY" : "MATCHDAYS"} ↓`}<span className="sr-only"> at {ground.venue_name}</span></summary>
      <ul>{matchdays.slice(1, limit + 1).map(row)}</ul>
      {matchdays.length > limit + 1 && <button type="button" onClick={() => setLimit(value => value + 5)} className="min-h-11 text-xs font-bold text-[var(--brand-interactive)] underline">MORE MATCHDAYS<span className="sr-only"> at {ground.venue_name}</span></button>}
    </details>}
  </div>;
}
