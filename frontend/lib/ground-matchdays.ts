import type { MyGround } from "../app/types/grounds.ts";

export function matchdayDate(value: string | null | undefined): string | null {
  const date = value?.match(/^\d{4}-\d{2}-\d{2}/)?.[0];
  if (!date || Number.isNaN(Date.parse(`${date}T00:00:00Z`)) || new Date(`${date}T00:00:00Z`).toISOString().slice(0, 10) !== date) return null;
  return date;
}

export function groundMatchdays(ground: MyGround) {
  const fixtures = new Map(ground.attended_fixtures.map(fixture => [fixture.fixture_id, fixture]));
  const seen = new Set<string>();
  return [...ground.visits]
    .sort((a, b) => (matchdayDate(b.visit_date) ?? "").localeCompare(matchdayDate(a.visit_date) ?? "") || b.visit_id - a.visit_id)
    .filter(visit => {
      const key = visit.fixture_id === null ? `visit:${visit.visit_id}` : `fixture:${visit.fixture_id}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map(visit => {
      const candidate = visit.fixture_id === null ? undefined : fixtures.get(visit.fixture_id);
      const fixture = candidate?.home_team?.trim() && candidate?.away_team?.trim() ? candidate : undefined;
      const date = matchdayDate(fixture?.fixture_date) ?? matchdayDate(visit.visit_date);
      const result = fixture && ["FT", "AET", "PEN"].includes(fixture.status ?? "") && Number.isInteger(fixture.home_goals) && Number.isInteger(fixture.away_goals) && fixture.home_goals! >= 0 && fixture.away_goals! >= 0 ? `${fixture.home_goals}–${fixture.away_goals}` : null;
      return { visitId: visit.visit_id, date, title: fixture ? `${fixture.home_team} v ${fixture.away_team}` : null, result,
        href: fixture ? `/fixture/${visit.fixture_id}` : `/venue/${ground.venue_id}`, fixtureLinked: Boolean(fixture) };
    });
}

export function formatMatchdayDate(date: string | null): string {
  return date ? new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${date}T00:00:00Z`)) : "DATE NOT RECORDED";
}
