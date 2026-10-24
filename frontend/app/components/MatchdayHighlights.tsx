export type MatchdayHighlightsData = {
  events: {
    kind: "goal" | "penalty" | "own_goal" | "missed_penalty" | "red_card";
    minute: number | null;
    extra: number | null;
    player: string | null;
    team: string;
    assist: string | null;
  }[];
  partial: boolean;
  score_reconciled: boolean;
};

const labels = {
  goal: "GOAL", penalty: "PENALTY GOAL", own_goal: "OWN GOAL",
  missed_penalty: "MISSED PENALTY", red_card: "RED CARD",
};

const symbols = {
  missed_penalty: "❌", red_card: "🟥",
};

function FootballIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="inline-block align-[-2px]" focusable="false">
    <circle cx="12" cy="12" r="9.5" stroke="currentColor" strokeWidth="1.4" />
    <path d="M12 7 16.7 10.4 14.9 15.9 9.1 15.9 7.3 10.4Z" fill="currentColor" />
    <path d="M12 2.5V7M20.8 8.4 16.7 10.4M17.7 19.6 14.9 15.9M6.3 19.6 9.1 15.9M3.2 8.4 7.3 10.4" stroke="currentColor" strokeWidth="1.4" />
  </svg>;
}

export default function MatchdayHighlights({ data, homeTeam, awayTeam }: {
  data?: MatchdayHighlightsData | null;
  homeTeam: string;
  awayTeam: string;
}) {
  if (!data?.score_reconciled || !data.events.length) return null;
  // The existing backend supplies the canonical fixture team's name on each event.
  // Never infer a side from a player, fuzzy-match names or guess ambiguous teams.
  if (homeTeam === awayTeam || data.events.some(event => event.team !== homeTeam && event.team !== awayTeam)) return null;
  return (
    <section aria-labelledby="matchday-highlights-heading" className="mt-5 border-t border-[var(--mg-green)]/25 pt-4 text-left text-[var(--mg-green)]">
      <h2 id="matchday-highlights-heading" className="mg-display-callout">MATCHDAY HIGHLIGHTS</h2>
      <div className="mt-3 grid grid-cols-[minmax(0,1fr)_3rem_minmax(0,1fr)] gap-x-1 text-xs font-bold leading-snug">
        <p className="min-w-0 break-words text-right">{homeTeam}</p>
        <span aria-hidden="true" />
        <p className="min-w-0 break-words">{awayTeam}</p>
      </div>
      <ol className="mt-1">
        {data.events.map((event, index) => {
          const home = event.team === homeTeam;
          const suffix = event.kind === "penalty" || event.kind === "missed_penalty" ? " (P)" : event.kind === "own_goal" ? " (OG)" : "";
          return <li key={index} className="grid grid-cols-[minmax(0,1fr)_3rem_minmax(0,1fr)] items-start gap-x-1 py-1">
            <span className="col-start-2 row-start-1 text-center text-xs font-semibold leading-[18px] tabular-nums">
              {event.minute === null ? "—" : `${event.minute}${event.extra ? `+${event.extra}` : ""}′`}
            </span>
            <div className={`row-start-1 min-w-0 break-words ${home ? "col-start-1 text-right" : "col-start-3 text-left"}`}>
              <p className="text-[13px] font-semibold leading-[18px]">
                <span className="sr-only">{event.team}: {labels[event.kind]}. </span>
                <span aria-hidden="true">{event.kind === "missed_penalty" || event.kind === "red_card" ? symbols[event.kind] : <FootballIcon />} </span>
                <span>{event.player || "Player not recorded"}</span><span aria-hidden="true">{suffix}</span>
              </p>
              {event.assist && <p className="text-[11px] leading-[15px] text-[var(--mg-ink)]/75">Assist: {event.assist}</p>}
            </div>
          </li>;
        })}
      </ol>
    </section>
  );
}
