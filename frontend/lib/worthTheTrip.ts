import type { Fixture } from "../app/types/fixture";
import { fixtureStatusGroup } from "./fixture-status";

export type Recommendation = {
  title: string;
  fixture: Fixture | null;
  metric: string | null;
  emptyMessage: string;
  showOverallRating?: boolean;
};

const TOP_FLIGHT_LEAGUE_IDS = new Set([39, 113, 253]);

function byKickoff(left: Fixture, right: Fixture) {
  return (
    new Date(left.fixture_date).getTime() -
    new Date(right.fixture_date).getTime()
  );
}

function choose(candidates: Fixture[], usedFixtureIds: Set<number>) {
  return (
    candidates.find(
      (fixture) => !usedFixtureIds.has(fixture.fixture_id)
    ) ?? candidates[0] ?? null
  );
}

export function buildWorthTheTripRecommendations(
  fixtures: Fixture[]
): Recommendation[] {
  const recommendationFixtures = fixtures.filter((fixture) => {
    const status = fixtureStatusGroup(fixture.status);
    return status === "upcoming" || status === "live";
  });
  const used = new Set<number>();
  const select = (candidates: Fixture[]) => {
    const fixture = choose(candidates, used);
    if (fixture) used.add(fixture.fixture_id);
    return fixture;
  };

  const rated = recommendationFixtures
    .filter((fixture) => fixture.away_day_score !== null)
    .sort(
      (left, right) =>
        (right.away_day_score ?? 0) - (left.away_day_score ?? 0) ||
        left.distance_miles - right.distance_miles ||
        byKickoff(left, right)
    );
  const bestRated = select(rated);

  const atmosphereRated = recommendationFixtures
    .filter((fixture) => fixture.atmosphere_score !== null)
    .sort(
      (left, right) =>
        (right.atmosphere_score ?? 0) - (left.atmosphere_score ?? 0) ||
        left.distance_miles - right.distance_miles ||
        byKickoff(left, right)
    );
  const bestAtmosphere = select(atmosphereRated);

  const closest = select(
    [...recommendationFixtures].sort(
      (left, right) =>
        left.distance_miles - right.distance_miles ||
        byKickoff(left, right)
    )
  );

  const hiddenGem = select(
    recommendationFixtures
      .filter(
        (fixture) =>
          !TOP_FLIGHT_LEAGUE_IDS.has(fixture.league_id) &&
          fixture.away_day_score !== null &&
          fixture.away_day_score >= 6
      )
      .sort(
        (left, right) =>
          (right.away_day_score ?? 0) - (left.away_day_score ?? 0) ||
          left.distance_miles - right.distance_miles ||
          byKickoff(left, right)
      )
  );

  return [
    {
      title: "🎟️ Best rated nearby",
      fixture: bestRated,
      metric: bestRated ? `🎟️ ${bestRated.away_day_score?.toFixed(1)} Terrace Rating` : null,
      emptyMessage: "Not enough ratings yet",
    },
    {
      title: "🥁 Best atmosphere",
      fixture: bestAtmosphere,
      metric: bestAtmosphere
        ? `Atmosphere ${bestAtmosphere.atmosphere_score?.toFixed(1)}`
        : null,
      emptyMessage: "Not enough atmosphere ratings yet",
    },
    {
      title: "🏠 Closest game",
      fixture: closest,
      metric: closest ? `${closest.distance_miles.toFixed(1)} mi away` : null,
      emptyMessage: "No qualifying fixtures nearby",
      showOverallRating: true,
    },
    {
      title: "💎 Hidden gem",
      fixture: hiddenGem,
      metric: hiddenGem ? `🎟️ ${hiddenGem.away_day_score?.toFixed(1)} Terrace Rating` : null,
      emptyMessage: "No hidden gem available yet",
    },
  ];
}
