import type { MyGround } from "../app/types/grounds";

export type GroundTimeframe = "30d" | "3m" | "1y" | "lifetime";

export const groundTimeframes: Array<{ key: GroundTimeframe; label: string }> = [
  { key: "30d", label: "30 days" },
  { key: "3m", label: "3 months" },
  { key: "1y", label: "1 year" },
  { key: "lifetime", label: "Lifetime" },
];

const cutoffFor = (timeframe: GroundTimeframe, now: Date) => {
  if (timeframe === "lifetime") return null;
  const cutoff = new Date(now);
  if (timeframe === "30d") cutoff.setDate(cutoff.getDate() - 30);
  if (timeframe === "3m") cutoff.setMonth(cutoff.getMonth() - 3);
  if (timeframe === "1y") cutoff.setFullYear(cutoff.getFullYear() - 1);
  return cutoff;
};

export function groundsInTimeframe(grounds: MyGround[], timeframe: GroundTimeframe, now = new Date()) {
  const cutoff = cutoffFor(timeframe, now);
  return grounds.flatMap((ground) => {
    const visits = ground.visits.filter((visit) => {
      if (cutoff === null) return true;
      return visit.visit_date !== null && new Date(`${visit.visit_date}T00:00:00`).getTime() >= cutoff.getTime();
    });
    if (visits.length === 0) return [];
    const dates = visits.flatMap((visit) => visit.visit_date ? [visit.visit_date] : []);
    const fixtureIds = new Set(visits.flatMap((visit) => visit.fixture_id === null ? [] : [visit.fixture_id]));
    return [{
      ...ground,
      visits,
      visit_count: visits.length,
      first_visit_date: dates.length ? dates.toSorted()[0] : null,
      latest_visit_date: dates.length ? dates.toSorted().at(-1) ?? null : null,
      has_undated_visit: visits.some((visit) => visit.visit_date === null),
      attended_fixtures: ground.attended_fixtures.filter((fixture) => fixtureIds.has(fixture.fixture_id)),
    }];
  });
}
