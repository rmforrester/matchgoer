import type { FootprintCompetition, FootprintSummary, MyGround } from "../app/types/grounds";

export type FootprintPeriod = "lifetime" | "season";

export function competitionGroundProgress(competition: FootprintCompetition): string | null {
  const total = competition.verified_ground_total;
  const count = competition.season_grounds;
  return competition.coverage === "ready" && Number.isInteger(total) && total! > 0 &&
    Number.isInteger(count) && count! >= 0 && count! <= total! ? `${count} / ${total} grounds` : null;
}

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
    const relevant = competition.grounds.flatMap(ground => {
      if (!ids.has(ground.venue_id)) return [];
      if (period === "season" && !ground.season_visit_ids.some(id => visits.has(id))) return [];
      if (ground.visit_ids != null) {
        const owned = ground.visit_ids.filter(id => visits.has(id));
        if (!owned.length) return [];
        return [{ ...ground, visit_ids: owned, season_visit_ids: ground.season_visit_ids.filter(id => visits.has(id)) }];
      }
      return [ground];
    });
    return relevant.length ? [{ ...competition, grounds: relevant }] : [];
  });
}
