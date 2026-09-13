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
