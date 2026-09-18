import assert from "node:assert/strict";
import test from "node:test";
import { matchingCompetitionGroups, supporterCompetitionGroup, supporterCompetitionGroups } from "./competitionGrouping.ts";

const inventory = [
  { country: "England", leagues: [{ league_id: 39, league_name: "Premier League" }, { league_id: 40, league_name: "Championship" }, { league_id: 45, league_name: "FA Cup" }] },
  { country: "France", leagues: [{ league_id: 61, league_name: "Ligue 1" }, { league_id: 62, league_name: "Ligue 2" }] },
  { country: "Germany", leagues: [{ league_id: 78, league_name: "Bundesliga" }, { league_id: 81, league_name: "DFB Pokal" }] },
  { country: "World", leagues: [{ league_id: 2, league_name: "UEFA Champions League" }, { league_id: 3, league_name: "UEFA Europa League" }, { league_id: 5, league_name: "UEFA Nations League" }, { league_id: 12, league_name: "CAF Champions League" }, { league_id: 13, league_name: "CONMEBOL Libertadores" }] },
];

test("search is case-insensitive, partial, and spans every geographic group", () => {
  for (const [query, expected] of [["CHAMP", 2], ["fa cup", 45], ["europa", 3], ["nations", 5], ["libertadores", 13]] as const) {
    assert.ok(matchingCompetitionGroups(supporterCompetitionGroups(inventory), query).flatMap(({ leagues }) => leagues).some(({ league_id }) => league_id === expected));
  }
});

test("confederation competitions receive supporter-facing continent groups", () => {
  const cases = [["UEFA Champions League", "Europe"], ["UEFA Nations League", "Europe"], ["CONMEBOL Libertadores", "South America"], ["CONCACAF Champions Cup", "North/Central America & Caribbean"], ["AFC Champions League", "Asia"], ["CAF Champions League", "Africa"], ["OFC Champions League", "Oceania"]] as const;
  for (const [name, expected] of cases) assert.equal(supporterCompetitionGroup("World", name), expected);
});

test("global and domestic competitions stay in their expected groups", () => {
  for (const name of ["FIFA World Cup", "FIFA Club World Cup", "CONMEBOL - UEFA Finalissima"]) assert.equal(supporterCompetitionGroup("World", name), "World");
  assert.equal(supporterCompetitionGroup("England", "Premier League"), "England");
  assert.equal(supporterCompetitionGroup("World", "Unclassified Competition"), "World");
});

test("regional World Cup qualification follows its confederation", () => {
  assert.equal(supporterCompetitionGroup("World", "World Cup - Qualification Europe"), "Europe");
  assert.equal(supporterCompetitionGroup("World", "World Cup - Qualification South America"), "South America");
  assert.equal(supporterCompetitionGroup("World", "World Cup - Qualification Asia"), "Asia");
});

test("search preserves geographic subsections and selectable competition IDs", () => {
  const grouped = supporterCompetitionGroups(inventory);
  assert.deepEqual(grouped.find(({ country }) => country === "Europe")?.leagues.map(({ league_id }) => league_id), [2, 3, 5]);
  assert.deepEqual(grouped.find(({ country }) => country === "England")?.leagues.map(({ league_id }) => league_id), [40, 45, 39]);
  assert.deepEqual(matchingCompetitionGroups(grouped, "champ"), [
    { country: "Africa", leagues: [{ league_id: 12, league_name: "CAF Champions League" }] },
    { country: "England", leagues: [{ league_id: 40, league_name: "Championship" }] },
    { country: "Europe", leagues: [{ league_id: 2, league_name: "UEFA Champions League" }] },
  ]);
});

test("searching a geographic group preserves the whole group", () => {
  const grouped = supporterCompetitionGroups(inventory);
  assert.deepEqual(matchingCompetitionGroups(grouped, "France"), [
    { country: "France", leagues: [{ league_id: 61, league_name: "Ligue 1" }, { league_id: 62, league_name: "Ligue 2" }] },
  ]);
  assert.deepEqual(matchingCompetitionGroups(grouped, "gErMaNy"), [
    { country: "Germany", leagues: [{ league_id: 78, league_name: "Bundesliga" }, { league_id: 81, league_name: "DFB Pokal" }] },
  ]);
  assert.deepEqual(matchingCompetitionGroups(grouped, "Ligue"), [
    { country: "France", leagues: [{ league_id: 61, league_name: "Ligue 1" }, { league_id: 62, league_name: "Ligue 2" }] },
  ]);
  assert.deepEqual(matchingCompetitionGroups(grouped, "no such competition"), []);
});
