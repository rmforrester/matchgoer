import { test } from "node:test";
import assert from "node:assert/strict";
import { groupPublicPhotos, mergePublicPhotos, groupFixturePhotos, mergeHistoricalGroups } from "./terraces-groups.ts";
import type { TerracePhoto } from "./terraces.ts";
const photo = (id: number, venue: number, time = "2026-10-16T12:00:00Z"): TerracePhoto => ({ photo_id:id, venue_id:venue, fixture_id:null, caption:null, display_name:"Matchgoer", match_date:null, home_team:null, away_team:null, published_at:time });
test("groups across pages without losing photos or repeating grounds", () => {
 const rows=mergePublicPhotos([photo(9,1),photo(8,2)], [photo(7,1),photo(6,3),photo(8,2)]);
 const groups=groupPublicPhotos(rows);
 assert.deepEqual(groups.map(g=>g.map(p=>p.photo_id)),[[9,7],[8],[6]]);
});
test("newest primary, stable timestamp ties, historical and independent contexts", () => {
 const old={...photo(5,1,"2020-01-01T00:00:00Z"),home_team:"Old home",away_team:"Old away",match_date:"1990-01-01"};
 const groups=groupPublicPhotos([old,photo(6,2),photo(7,1)]);
 assert.deepEqual(groups.map(g=>g[0].photo_id),[7,6]);assert.equal(groups[0][1].home_team,"Old home");
 assert.equal(groups[0][1].match_date,"1990-01-01");
});
test("refreshed signed image replaces duplicate rather than losing refresh", () => {
 assert.equal(mergePublicPhotos([photo(1,1)],[{...photo(1,1),image_url:"synthetic:new"}])[0].image_url,"synthetic:new");
});
test("distinct display names never used as grouping identity",()=>{
 assert.equal(groupPublicPhotos([photo(1,1),photo(2,2)]).length,2);
 assert.equal(groupPublicPhotos([photo(1,1),{...photo(2,1),display_name:"Someone else"}]).length,1);
});


test("exact fixtures group across contributors and cursor pages, never by ground", () => {
 const rows=mergePublicPhotos([{...photo(9,1),fixture_id:11},{...photo(8,1),fixture_id:12}], [{...photo(7,1),fixture_id:11,display_name:"Other supporter"},{...photo(9,1),fixture_id:11}]);
 assert.deepEqual(groupFixturePhotos(rows).map(g=>g.map(p=>p.photo_id)),[[9,7],[8]]);
});
test("unlinked photos remain independent until server confirms a shared matchday", () => {
 const rows=[photo(9,1),photo(8,1),photo(7,1)];
 assert.equal(groupFixturePhotos(rows).length,3);
 const groups=mergeHistoricalGroups({},[9,7]);
 assert.deepEqual(groupFixturePhotos(rows,groups).map(g=>g.map(p=>p.photo_id)),[[9,7],[8]]);
});
test("overlapping confirmed historical pages unite without affecting unrelated visits", () => {
 const groups=mergeHistoricalGroups(mergeHistoricalGroups({},[9,7]),[7,6]);
 assert.deepEqual(groupFixturePhotos([photo(9,1),photo(8,1),photo(7,1),photo(6,1)],groups).map(g=>g.map(p=>p.photo_id)),[[9,7,6],[8]]);
});
