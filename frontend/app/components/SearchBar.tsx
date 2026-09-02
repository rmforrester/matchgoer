import { useEffect, useRef, useState } from "react";

import { endDateAtOrAfterStart } from "../../lib/fixtureDiscovery";

type League = { league_id: number; league_name: string };

export type LeagueGroup = { country: string; leagues: League[] };

type DateRangeProps = {
  startDate: string;
  setStartDate: (date: string) => void;
  minimumStartDate: string;
  endDate: string;
  setEndDate: (date: string) => void;
};

export function DateRangeFields({ startDate, setStartDate, minimumStartDate, endDate, setEndDate }: DateRangeProps) {
  const toDateInput = useRef<HTMLInputElement>(null);
  const openToPickerAfterUpdate = useRef(false);
  const [toNeedsAttention, setToNeedsAttention] = useState(false);

  useEffect(() => {
    if (!openToPickerAfterUpdate.current) return;
    openToPickerAfterUpdate.current = false;
    const toInput = toDateInput.current;
    if (!toInput) return;
    toInput.focus({ preventScroll: true });
    try {
      toInput.showPicker?.();
    } catch {
      // Native pickers may reject programmatic opening, notably on iOS Safari.
    }
  }, [endDate, startDate]);

  return (
    <div className="grid min-w-0 grid-cols-2 items-end gap-2">
      <label className="grid min-w-0 gap-1 text-xs font-extrabold uppercase tracking-[0.12em]">
        From
        <input
          type="date"
          value={startDate}
          min={minimumStartDate}
          className="tt-control w-full min-w-0 max-w-full px-2 [color-scheme:light] sm:px-3"
          onChange={(event) => {
            const nextStartDate = event.target.value && event.target.value < minimumStartDate ? minimumStartDate : event.target.value;
            setStartDate(nextStartDate);
            setEndDate(endDateAtOrAfterStart(nextStartDate, endDate));
            setToNeedsAttention(Boolean(nextStartDate));
            openToPickerAfterUpdate.current = Boolean(nextStartDate);
          }}
        />
      </label>

      <label className={`grid min-w-0 gap-1 text-xs font-extrabold uppercase tracking-[0.12em] ${toNeedsAttention ? "text-[var(--tt-blue)]" : ""}`}>
        To
        <input
          ref={toDateInput}
          type="date"
          value={endDate}
          min={startDate || minimumStartDate}
          className={`tt-control w-full min-w-0 max-w-full px-2 [color-scheme:light] sm:px-3 ${toNeedsAttention ? "border-2 border-[var(--tt-blue)] shadow-[2px_2px_0_var(--tt-blue)]" : ""}`}
          onChange={(event) => {
            setEndDate(event.target.value);
            setToNeedsAttention(false);
          }}
        />
      </label>
    </div>
  );
}

type Props = {
  leagues: LeagueGroup[];
  selectedLeagueIds: number[];
  setSelectedLeagueIds: (leagueIds: number[]) => void;
  radius: number;
  setRadius: (radius: number) => void;
};

export default function SearchBar({ leagues, selectedLeagueIds, setSelectedLeagueIds, radius, setRadius }: Props) {
  const selected = new Set(selectedLeagueIds);
  const toggleLeague = (leagueId: number) => setSelectedLeagueIds(
    selected.has(leagueId) ? selectedLeagueIds.filter((id) => id !== leagueId) : [...selectedLeagueIds, leagueId]
  );

  return (
    <div className="grid min-w-0 gap-2.5 sm:grid-cols-[0.8fr_1.2fr]">
      <label className="grid min-w-0 gap-1 text-xs font-extrabold uppercase tracking-[0.12em]">
        Distance
        <select value={radius} onChange={(event) => setRadius(Number(event.target.value))} className="tt-control w-full min-w-0 px-3 [color-scheme:light]">
          <option value={10}>Local · 10 mi scale</option>
          <option value={25}>City · 25 mi scale</option>
          <option value={50}>Region · 50 mi scale</option>
          <option value={100}>Wide · 100 mi scale</option>
        </select>
      </label>

      <div className="grid min-w-0 gap-1 text-xs font-bold uppercase tracking-[0.1em] text-[var(--tt-muted)]">
        League <span className="normal-case tracking-normal">Optional</span>
        <details className="relative">
          <summary className="flex min-h-10 cursor-pointer list-none items-center justify-between border border-[var(--tt-rule)] bg-[var(--tt-newsprint)] px-3 font-medium normal-case tracking-normal text-[var(--tt-ink)] marker:content-none hover:border-[var(--tt-ink)]">
            <span>{selectedLeagueIds.length === 0 ? "All leagues" : `${selectedLeagueIds.length} ${selectedLeagueIds.length === 1 ? "league" : "leagues"} selected`}</span><span aria-hidden="true">▾</span>
          </summary>
          <div className="absolute left-0 z-[1000] mt-1 max-h-80 w-[min(20rem,calc(100vw-3rem))] overflow-y-auto border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] p-3 shadow-[4px_4px_0_var(--tt-blue)] sm:left-auto sm:right-0">
            <button type="button" onClick={() => setSelectedLeagueIds([])} className="mb-3 min-h-11 w-full border border-[var(--tt-ink)] px-3 text-left text-xs font-extrabold uppercase hover:bg-[var(--tt-blue)] hover:text-[var(--tt-paper)]">All leagues</button>
            <div className="space-y-4">
              {leagues.map((group) => <fieldset key={group.country}>
                <legend className="mb-1 text-xs font-extrabold uppercase tracking-[0.12em] text-[var(--tt-blue)]">{group.country}</legend>
                <div className="space-y-1">{group.leagues.map((league) => <label key={`${group.country}-${league.league_id}`} className="flex min-h-9 cursor-pointer items-center gap-2 text-sm font-medium normal-case tracking-normal">
                  <input type="checkbox" checked={selected.has(league.league_id)} onChange={() => toggleLeague(league.league_id)} className="h-4 w-4 accent-[var(--tt-blue)]" /><span>{league.league_name}</span>
                </label>)}</div>
              </fieldset>)}
            </div>
          </div>
        </details>
      </div>
    </div>
  );
}
