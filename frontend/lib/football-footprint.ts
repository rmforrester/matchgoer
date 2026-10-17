import type { FootprintCompetition, FootprintSummary, MyGround } from "../app/types/grounds";

export type FootprintPeriod = "lifetime" | "season";

/** One owned-visit projection feeds map, counters, passport and ground cards. */
export function footprintGrounds(grounds: MyGround[], period: FootprintPeriod, footprint: FootprintSummary | null): MyGround[] {
  if (period === "lifetime") return grounds;
  const eligible = new Set(footprint?.season_visit_ids ?? []);
  return grounds.flatMap(ground => {
    const visits = ground.visits.filter(visit => visit.visit_date !== null && eligible.has(visit.visit_id));
    if (!visits.length) return [];
    const dates = visits.map(visit => visit.visit_date!).toSorted();
    const fixtureIds = new Set(visits.map(visit => visit.fixture_id));
    return [{ ...ground, visits, visit_count: visits.length, first_visit_date: dates[0],
      latest_visit_date: dates.at(-1)!, has_undated_visit: false,
      attended_fixtures: ground.attended_fixtures.filter(fixture => fixtureIds.has(fixture.fixture_id)) }];
  });
}

export function competitionsForGrounds(competitions: FootprintCompetition[], grounds: MyGround[], period: FootprintPeriod) {
  const ids = new Set(grounds.map(ground => ground.venue_id));
  const visits = new Set(grounds.flatMap(ground => ground.visits.map(visit => visit.visit_id)));
  return competitions.flatMap(competition => {
    const relevant = competition.grounds.filter(ground => ids.has(ground.venue_id) &&
      (period === "lifetime" || ground.season_visit_ids.some(id => visits.has(id))));
    return relevant.length ? [{ ...competition, grounds: relevant }] : [];
  });
}
