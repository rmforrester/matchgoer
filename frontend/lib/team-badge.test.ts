import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const root = process.cwd();
const badgeSource = fs.readFileSync(path.join(root, "app/components/TeamBadge.tsx"), "utf8");
const teamsSource = fs.readFileSync(path.join(root, "app/components/FixtureTeams.tsx"), "utf8");
const fixtureSource = fs.readFileSync(path.join(root, "app/fixture/[fixtureId]/page.tsx"), "utf8");
const discoverResultsSource = fs.readFileSync(path.join(root, "app/components/NearbyFixtureCarousel.tsx"), "utf8");

test("badge collapses cleanly for missing sources and image failures", () => {
  assert.match(badgeSource, /if \(!src \|\| failedSrc === src\) return null/);
  assert.match(badgeSource, /onError=\{\(\) => setFailedSrc\(src\)\}/);
  assert.match(badgeSource, /alt=""/);
  assert.match(badgeSource, /aria-hidden="true"/);
});

test("badge preserves transparent and extreme-aspect assets without recolouring", () => {
  assert.match(badgeSource, /object-contain/);
  assert.doesNotMatch(badgeSource, /filter:|grayscale|sepia|hue-rotate/);
});

test("fixture team layout remains optional, responsive, and long-name safe", () => {
  assert.match(teamsSource, /homeBadgeSrc\?: string \| null/);
  assert.match(teamsSource, /awayBadgeSrc\?: string \| null/);
  assert.match(teamsSource, /min-w-0 break-words/);
  assert.match(teamsSource, /h-12 w-12 sm:h-16 sm:w-16/);
});

test("fixture hero and Discover results opt into canonical proxy badge paths", () => {
  assert.match(fixtureSource, /apiAssetUrl\(data\.fixture\.home_team_badge_url\)/);
  assert.match(fixtureSource, /apiAssetUrl\(data\.fixture\.away_team_badge_url\)/);
  assert.match(fixtureSource, /homeBadgeSrc=/);
  assert.match(fixtureSource, /awayBadgeSrc=/);
  assert.match(discoverResultsSource, /apiAssetUrl\(fixture\.home_team_badge_url\)/);
  assert.match(discoverResultsSource, /apiAssetUrl\(fixture\.away_team_badge_url\)/);
});
