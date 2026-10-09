import type { MyGround } from "../app/types/grounds";

export type GroundTimeframe = "30d" | "3m" | "1y" | "lifetime";

export const groundTimeframes: Array<{ key: GroundTimeframe; label: string }> = [
  { key: "30d", label: "30 days" },
  { key: "3m", label: "3 months" },
  { key: "1y", label: "1 year" },
  { key: "lifetime", label: "Lifetime" },
];

export function footballCountry(label: string | null): { key: string; name: string } | null {
  const name = label?.trim();
  if (!name || name.toLowerCase() === "world") return null;
  const key = name.toLowerCase();
  if (["us", "usa", "united states"].includes(key)) return { key: "united states", name: "United States" };
  if (["uk", "united kingdom"].includes(key)) return { key: "united kingdom", name: "United Kingdom" };
  if (["northern-ireland", "northern ireland"].includes(key)) return { key: "northern ireland", name: "Northern Ireland" };
  return { key, name };
}

export function footballPassport(grounds: MyGround[]) {
  const countries = new Map<string, { key: string; name: string; grounds: Set<number>; visits: Set<number> }>();
  for (const ground of grounds) {
    const country = footballCountry(ground.venue_country);
    if (!country || ground.visits.length === 0) continue;
    const entry = countries.get(country.key) ?? { ...country, grounds: new Set<number>(), visits: new Set<number>() };
    // Keep an input-order-independent display label when casing differs.
    if (country.name < entry.name) entry.name = country.name;
    entry.grounds.add(ground.venue_id);
    for (const visit of ground.visits) entry.visits.add(visit.visit_id);
    countries.set(country.key, entry);
  }
  return [...countries.values()].map(({ key, name, grounds, visits }) => ({ key, name, groundCount: grounds.size, matchdayCount: visits.size }))
    .sort((a, b) => b.matchdayCount - a.matchdayCount || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
}

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
