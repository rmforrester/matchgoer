import assert from "node:assert/strict";
import test from "node:test";
import { competitionGroundProgress } from "./football-footprint.ts";
import type { FootprintCompetition } from "../app/types/grounds.ts";
const ready = { coverage: "ready", verified_ground_total: 12, season_grounds: 1 } as FootprintCompetition;
test("verified season progress counts grounds, not clubs", () => {
  assert.equal(competitionGroundProgress(ready), "1 / 12 grounds");
  assert.equal(competitionGroundProgress({ ...ready, total_clubs: 24 }), "1 / 12 grounds");
});
test("unknown, incomplete, legacy and invalid totals leave progress blank", () => {
  for (const row of [{ ...ready, coverage: "attendance" }, { ...ready, coverage: "incomplete" },
    { ...ready, verified_ground_total: null }, { ...ready, verified_ground_total: undefined },
    { ...ready, verified_ground_total: 0 }, { ...ready, season_grounds: 13 }, { ...ready, season_grounds: null }]) {
    assert.equal(competitionGroundProgress(row as FootprintCompetition), null);
  }
});
