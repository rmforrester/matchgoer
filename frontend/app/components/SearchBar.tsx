import { useMemo, useState } from "react";

import { localCalendarDateValue, upcomingWeekendDateRange } from "../../lib/fixtureDiscovery";

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
  const [open, setOpen] = useState(false);
  const [choosingEnd, setChoosingEnd] = useState(false);
  const [draftStart, setDraftStart] = useState(startDate);
  const [draftEnd, setDraftEnd] = useState(endDate);
  const [month, setMonth] = useState(() => monthStart(startDate || minimumStartDate));
  const days = useMemo(() => calendarDays(month), [month]);
  const openCalendar = () => {
    setDraftStart(startDate);
    setDraftEnd(endDate);
    setChoosingEnd(false);
    setMonth(monthStart(startDate || minimumStartDate));
    setOpen(true);
  };
  const commit = (nextStart: string, nextEnd: string) => {
    setStartDate(nextStart);
    setEndDate(nextEnd);
    setOpen(false);
    setChoosingEnd(false);
  };
  const selectDay = (day: string) => {
    if (!choosingEnd) {
      setDraftStart(day);
      setDraftEnd(day);
      setChoosingEnd(true);
      return;
    }
    if (day < draftStart) {
      setDraftStart(day);
      setDraftEnd(day);
      return;
    }
    commit(draftStart, day);
  };
  const shortcut = (kind: "today" | "tomorrow" | "weekend" | "next-weekend") => {
    const now = new Date();
    if (kind === "today") return commit(localCalendarDateValue(now), localCalendarDateValue(now));
    if (kind === "tomorrow") {
      const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
      return commit(localCalendarDateValue(tomorrow), localCalendarDateValue(tomorrow));
    }
    const weekend = upcomingWeekendDateRange(now);
    if (kind === "weekend") return commit(weekend.startDate, weekend.endDate);
    commit(addCalendarDays(weekend.startDate, 7), addCalendarDays(weekend.endDate, 7));
  };

  return (
    <div className="min-w-0">
      <button type="button" onClick={openCalendar} aria-haspopup="dialog" aria-expanded={open} className="tt-control flex w-full min-w-0 items-center justify-between gap-3 px-4 py-2 text-left text-base font-bold normal-case tracking-normal">
        <span>{formatRange(startDate, endDate)}</span><span aria-hidden="true">▾</span>
      </button>
      {open && <div className="fixed inset-0 z-[2000] flex items-end bg-black/40 p-2 sm:items-center sm:justify-center" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
        <section role="dialog" aria-modal="true" aria-label="Choose match dates" className="max-h-[calc(100dvh-1rem)] w-full overflow-y-auto border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] p-3 shadow-[5px_5px_0_var(--brand-interactive)] sm:max-w-md sm:p-4">
          <div className="flex items-center justify-between gap-3"><div><p className="tt-kicker">Choose dates</p><p className="mt-1 text-sm font-bold">{choosingEnd ? "Now choose an end date" : "Choose a start date"}</p></div><button type="button" onClick={() => setOpen(false)} aria-label="Close calendar" className="grid h-11 w-11 place-items-center border-2 border-[var(--tt-ink)] text-2xl">×</button></div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">{([['Today','today'],['Tomorrow','tomorrow'],['This weekend','weekend'],['Next weekend','next-weekend']] as const).map(([label, kind]) => <button key={kind} type="button" onClick={() => shortcut(kind)} className="min-h-11 border border-[var(--tt-ink)] px-2 text-xs font-extrabold uppercase hover:bg-[var(--brand-interactive)] hover:text-white">{label}</button>)}</div>
          <div className="mt-4 flex items-center justify-between"><button type="button" onClick={() => setMonth(addMonths(month, -1))} disabled={month <= monthStart(minimumStartDate)} className="grid h-11 w-11 place-items-center disabled:opacity-30" aria-label="Previous month">←</button><h3 className="font-extrabold uppercase tracking-wide">{formatMonth(month)}</h3><button type="button" onClick={() => setMonth(addMonths(month, 1))} className="grid h-11 w-11 place-items-center" aria-label="Next month">→</button></div>
          <div className="mt-2 grid grid-cols-7 text-center text-[0.65rem] font-extrabold uppercase text-[var(--tt-muted)]">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((day) => <span key={day}>{day}</span>)}</div>
          <div className="mt-1 grid grid-cols-7 gap-1">{days.map(({ value, currentMonth }) => { const disabled = value < minimumStartDate; const inRange = Boolean(draftStart && draftEnd && value >= draftStart && value <= draftEnd); const edge = value === draftStart || value === draftEnd; return <button key={value} type="button" disabled={disabled} onClick={() => selectDay(value)} aria-label={formatDayLabel(value)} aria-pressed={inRange} className={`min-h-11 border text-sm font-bold disabled:opacity-20 ${!currentMonth ? 'text-[var(--tt-muted)]' : ''} ${inRange ? 'border-[var(--brand-interactive)] bg-[var(--brand-primary-subtle)]' : 'border-transparent'} ${edge ? 'bg-[var(--brand-interactive)] text-white' : ''}`}>{Number(value.slice(8))}</button>; })}</div>
          <p className="mt-3 text-center text-xs font-bold text-[var(--tt-muted)]">Tap the same date twice for one day.</p>
        </section>
      </div>}
    </div>
  );
}

function parseCalendarDate(value: string) { const [year, month, day] = value.split("-").map(Number); return new Date(year, month - 1, day || 1, 12); }
function monthStart(value: string) { const date = parseCalendarDate(value); return localCalendarDateValue(new Date(date.getFullYear(), date.getMonth(), 1, 12)); }
function addCalendarDays(value: string, amount: number) { const date = parseCalendarDate(value); date.setDate(date.getDate() + amount); return localCalendarDateValue(date); }
function addMonths(value: string, amount: number) { const date = parseCalendarDate(value); return localCalendarDateValue(new Date(date.getFullYear(), date.getMonth() + amount, 1, 12)); }
function calendarDays(value: string) { const first = parseCalendarDate(monthStart(value)); const offset = (first.getDay() + 6) % 7; return Array.from({ length: 42 }, (_, index) => { const date = new Date(first); date.setDate(1 - offset + index); return { value: localCalendarDateValue(date), currentMonth: date.getMonth() === first.getMonth() }; }); }
function formatMonth(value: string) { return parseCalendarDate(value).toLocaleDateString(undefined, { month: "long", year: "numeric" }); }
function formatDayLabel(value: string) { return parseCalendarDate(value).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" }); }
function formatRange(start: string, end: string) { if (!start || !end) return "Choose dates"; const startLabel = parseCalendarDate(start).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }); if (start === end) return startLabel; return `${startLabel} – ${parseCalendarDate(end).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}`; }

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
      <label className="grid min-w-0 gap-1 text-xs font-bold uppercase tracking-[0.1em] text-[var(--tt-muted)]">
        Distance <span className="text-[0.65rem] font-medium normal-case tracking-normal">Optional</span>
        <select value={radius} onChange={(event) => setRadius(Number(event.target.value))} className="tt-control w-full min-w-0 px-3 font-medium normal-case tracking-normal text-[var(--tt-ink)] [color-scheme:light]">
          <option value={10}>Local · 10 mi scale</option>
          <option value={25}>City · 25 mi scale</option>
          <option value={50}>Region · 50 mi scale</option>
          <option value={100}>Wide · 100 mi scale</option>
        </select>
      </label>

      <div className="grid min-w-0 gap-1 text-xs font-bold uppercase tracking-[0.1em] text-[var(--tt-muted)]">
        League <span className="text-[0.65rem] font-medium normal-case tracking-normal">Optional</span>
        <details className="group relative">
          <summary className="flex min-h-10 cursor-pointer list-none items-center justify-between border border-[var(--tt-rule)] bg-[var(--tt-newsprint)] px-3 font-medium normal-case tracking-normal text-[var(--tt-ink)] marker:content-none hover:border-[var(--tt-ink)]">
            <span>{selectedLeagueIds.length === 0 ? "All leagues" : `${selectedLeagueIds.length} ${selectedLeagueIds.length === 1 ? "league" : "leagues"} selected`}</span><span aria-hidden="true">▾</span>
          </summary>
          <div className="tt-league-options mt-1 overflow-y-auto border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] p-3 shadow-[3px_3px_0_var(--brand-interactive)]">
            <button type="button" onClick={() => setSelectedLeagueIds([])} className="mb-3 min-h-11 w-full border border-[var(--tt-ink)] px-3 text-left text-xs font-extrabold uppercase hover:bg-[var(--brand-interactive)] hover:text-[var(--tt-paper)]">All leagues</button>
            <div className="space-y-4">
              {leagues.map((group) => <fieldset key={group.country}>
                <legend className="mb-1 text-xs font-extrabold uppercase tracking-[0.12em] text-[var(--brand-interactive)]">{group.country}</legend>
                <div className="space-y-1">{group.leagues.map((league) => <label key={`${group.country}-${league.league_id}`} className="flex min-h-9 cursor-pointer items-center gap-2 text-sm font-medium normal-case tracking-normal">
                  <input type="checkbox" checked={selected.has(league.league_id)} onChange={() => toggleLeague(league.league_id)} className="h-4 w-4 accent-[var(--brand-interactive)]" /><span>{league.league_name}</span>
                </label>)}</div>
              </fieldset>)}
            </div>
          </div>
        </details>
      </div>
    </div>
  );
}
