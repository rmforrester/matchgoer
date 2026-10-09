export const UPCOMING_PREVIEW_LIMIT = 3;
export const ANSWER_PREVIEW_LIMIT = 2;
export const PAST_PREVIEW_LIMIT = 6;

export type ResultFields = {
  status?: string | null;
  home_goals?: number | null;
  away_goals?: number | null;
};

export function trustworthyScore(fixture: ResultFields): string | null {
  const finished = new Set(["FT", "AET", "PEN"]).has((fixture.status ?? "").toUpperCase());
  return finished && fixture.home_goals != null && fixture.away_goals != null
    ? `${fixture.home_goals}–${fixture.away_goals}`
    : null;
}

export function previewItems<T>(items: T[], limit: number, expanded: boolean): T[] {
  return expanded ? items : items.slice(0, limit);
}

type SavedMatch = { fixture_id: number; fixture_date: string; status?: string | null; going?: boolean };
const excludedConfirmation = new Set(["PST", "CANC", "ABD", "AWD", "WO", "1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"]);

export function canConfirmAttendance(fixture: SavedMatch, now: Date): boolean {
  const kickoff = new Date(fixture.fixture_date).getTime();
  return Number.isFinite(kickoff) && now.getTime() >= kickoff + 3 * 60 * 60 * 1000
    && !excludedConfirmation.has((fixture.status ?? "").toUpperCase());
}

export function partitionMatchdays<T extends SavedMatch>(saved: T[], attendedIds: Set<number>, now: Date) {
  const unique = [...new Map(saved.map((fixture) => [fixture.fixture_id, fixture])).values()]
    .filter((fixture) => !attendedIds.has(fixture.fixture_id));
  const awaiting = unique.filter((fixture) => canConfirmAttendance(fixture, now))
    .sort((a, b) => Number(Boolean(b.going)) - Number(Boolean(a.going)) || new Date(b.fixture_date).getTime() - new Date(a.fixture_date).getTime());
  const awaitingIds = new Set(awaiting.map((fixture) => fixture.fixture_id));
  const remaining = unique.filter((fixture) => !awaitingIds.has(fixture.fixture_id))
    .sort((a, b) => new Date(a.fixture_date).getTime() - new Date(b.fixture_date).getTime());
  return { going: remaining.filter((fixture) => fixture.going), interested: remaining.filter((fixture) => !fixture.going), awaiting };
}
