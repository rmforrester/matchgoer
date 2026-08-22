type League = {
  league_id: number;
  league_name: string;
};

export type LeagueGroup = {
  country: string;
  leagues: League[];
};

type Props = {
  leagues: LeagueGroup[];
  selectedLeagueIds: number[];
  setSelectedLeagueIds: (leagueIds: number[]) => void;
  radius: number;
  setRadius: (radius: number) => void;
  startDate: string;
  setStartDate: (date: string) => void;
  minimumStartDate: string;
  endDate: string;
  setEndDate: (date: string) => void;
};

export default function SearchBar({
  leagues,
  selectedLeagueIds,
  setSelectedLeagueIds,
  radius,
  setRadius,
  startDate,
  setStartDate,
  minimumStartDate,
  endDate,
  setEndDate,
}: Props) {
  const selected = new Set(selectedLeagueIds);
  const toggleLeague = (leagueId: number) => {
    setSelectedLeagueIds(
      selected.has(leagueId)
        ? selectedLeagueIds.filter((id) => id !== leagueId)
        : [...selectedLeagueIds, leagueId]
    );
  };

  return (
    <div className="grid min-w-0 grid-cols-2 gap-2.5 lg:grid-cols-[1fr_1fr_.7fr_1.2fr]">
      <label className="grid min-w-0 gap-1 text-xs font-extrabold uppercase tracking-[0.12em]">
        From
        <input
          type="date"
          value={startDate}
          min={minimumStartDate}
          className="tt-control w-full min-w-0 px-3 [color-scheme:light]"
          onChange={(event) => setStartDate(
            event.target.value && event.target.value < minimumStartDate
              ? minimumStartDate
              : event.target.value
          )}
        />
      </label>

      <label className="grid min-w-0 gap-1 text-xs font-extrabold uppercase tracking-[0.12em]">
        To
        <input
          type="date"
          value={endDate}
          className="tt-control w-full min-w-0 px-3 [color-scheme:light]"
          onChange={(event) => setEndDate(event.target.value)}
        />
      </label>

      <label className="col-span-1 grid min-w-0 gap-1 text-xs font-extrabold uppercase tracking-[0.12em]">
        Distance
        <select
          value={radius}
          onChange={(event) => setRadius(Number(event.target.value))}
          className="tt-control w-full min-w-0 px-3 [color-scheme:light]"
        >
          <option value={10}>Local · 10 mi scale</option>
          <option value={25}>City · 25 mi scale</option>
          <option value={50}>Region · 50 mi scale</option>
          <option value={100}>Wide · 100 mi scale</option>
        </select>
      </label>

      <div className="col-span-2 grid min-w-0 gap-1 text-xs font-bold uppercase tracking-[0.1em] text-[var(--tt-muted)] lg:col-span-1">
        League <span className="normal-case tracking-normal">Optional</span>
        <details className="relative">
          <summary className="flex min-h-10 cursor-pointer list-none items-center justify-between border border-[var(--tt-rule)] bg-[var(--tt-newsprint)] px-3 font-medium normal-case tracking-normal text-[var(--tt-ink)] marker:content-none hover:border-[var(--tt-ink)]">
            <span>{selectedLeagueIds.length === 0 ? "All leagues" : `${selectedLeagueIds.length} ${selectedLeagueIds.length === 1 ? "league" : "leagues"} selected`}</span>
            <span aria-hidden="true">▾</span>
          </summary>
          <div className="absolute left-0 z-[1000] mt-1 max-h-80 w-[min(20rem,calc(100vw-3rem))] overflow-y-auto border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] p-3 shadow-[4px_4px_0_var(--tt-blue)] lg:left-auto lg:right-0">
            <button
              type="button"
              onClick={() => setSelectedLeagueIds([])}
              className="mb-3 min-h-11 w-full border border-[var(--tt-ink)] px-3 text-left text-xs font-extrabold uppercase hover:bg-[var(--tt-blue)] hover:text-[var(--tt-paper)]"
            >
              All leagues
            </button>
            <div className="space-y-4">
              {leagues.map((group) => (
                <fieldset key={group.country}>
                  <legend className="mb-1 text-xs font-extrabold uppercase tracking-[0.12em] text-[var(--tt-blue)]">{group.country}</legend>
                  <div className="space-y-1">
                    {group.leagues.map((league) => (
                      <label key={`${group.country}-${league.league_id}`} className="flex min-h-9 cursor-pointer items-center gap-2 text-sm font-medium normal-case tracking-normal">
                        <input
                          type="checkbox"
                          checked={selected.has(league.league_id)}
                          onChange={() => toggleLeague(league.league_id)}
                          className="h-4 w-4 accent-[var(--tt-blue)]"
                        />
                        <span>{league.league_name}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              ))}
            </div>
          </div>
        </details>
      </div>
    </div>
  );
}
