import { test } from "node:test";
import assert from "node:assert/strict";
import { publicMatchdayParams, viewerStepIndex } from "./terraces-viewer.ts";
import { mergePublicPhotos } from "./terraces-groups.ts";
import type { TerracePhoto } from "./terraces.ts";

const photo = (photo_id: number, fixture_id: number | null = 50): TerracePhoto => ({ photo_id, fixture_id, venue_id: 9, caption: null, display_name: "Synthetic", match_date: null, home_team: null, away_team: null, published_at: "2026-10-16T12:00:00Z" });
test("known fixture reuses bounded venue/fixture public pagination", () => {
  assert.deepEqual(publicMatchdayParams(photo(3), "opaque"), { limit: 24, cursor: "opaque", venue_id: 9, fixture_id: 50 });
});
test("unknown fixture uses a public photo anchor, never a private visit or date", () => {
  const params = publicMatchdayParams({ ...photo(3, null), match_date: "2001-07-03" });
  assert.deepEqual(params, { limit: 24, cursor: undefined, matchday_of: 3 });
  assert.equal("visit_id" in params, false);
});
test("viewer steps do not wrap, invent positions or duplicate paginated records", () => {
  const rows = mergePublicPhotos([photo(4), photo(3)], [photo(3), photo(2), photo(1)]);
  assert.deepEqual(rows.map(p => p.photo_id), [4, 3, 2, 1]);
  assert.equal(viewerStepIndex(rows, 4, -1), null);
  assert.equal(viewerStepIndex(rows, 3, 1), 2);
  assert.equal(viewerStepIndex(rows, 1, 1), null);
  assert.equal(viewerStepIndex(rows, 99, 1), 0);
  assert.equal(viewerStepIndex(rows, 99, -1), null);
});
