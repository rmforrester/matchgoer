import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  applyMapAreaOrigin,
  applyUserLocationEvent,
  beginGeolocationTransition,
  buildViewportDiscoveryParams,
  compactFixtureCard,
  discoveryZoomForRadius,
  endDateAtOrAfterStart,
  FIXTURE_POPUP_BEHAVIOR,
  fixtureGroupDecision,
  geolocationErrorMessage,
  GEOLOCATION_INSECURE_MESSAGE,
  GEOLOCATION_UNSUPPORTED_MESSAGE,
  isCurrentDiscoveryRequest,
  localCalendarDateValue,
  manualCurrentLocationOrigin,
  nextFourteenDaysDateRange,
  resolvedLocationTransition,
  upcomingWeekendDateRange,
  groupFixturesByVenue,
  type DiscoveryViewport,
} from "./fixtureDiscovery.ts";
import type { Fixture } from "../app/types/fixture.ts";
import { USER_MARKER_DESIGN, VENUE_MARKER_DESIGN, venueMarkerPresentation } from "./mapMarkerDesign.ts";
import { discoverTileLayerConfig } from "./discoverMapTiles.ts";

const miamiViewport: DiscoveryViewport = {
  center: { latitude: 25.7741566, longitude: -80.1935973 },
  north: 26.3241566,
  south: 25.2241566,
  east: -79.4435973,
  west: -80.9435973,
};

const discoverPageSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
const searchBarSource = readFileSync(new URL("../app/components/SearchBar.tsx", import.meta.url), "utf8");
const fixtureMapSource = readFileSync(new URL("../app/components/FixtureMap.tsx", import.meta.url), "utf8");
const fixtureCarouselSource = readFileSync(new URL("../app/components/NearbyFixtureCarousel.tsx", import.meta.url), "utf8");
const fixturePageSource = readFileSync(new URL("../app/fixture/[fixtureId]/page.tsx", import.meta.url), "utf8");
const groundMarkerSource = readFileSync(new URL("../app/components/groundMarkerIcon.ts", import.meta.url), "utf8");
const shortlistSource = readFileSync(new URL("../app/components/DiscoverShortlist.tsx", import.meta.url), "utf8");
const matchdaysSource = readFileSync(new URL("../app/components/InterestedTab.tsx", import.meta.url), "utf8");
const groundsSource = readFileSync(new URL("../app/components/VisitedTab.tsx", import.meta.url), "utf8");
const groundPageSource = readFileSync(new URL("../app/venue/[venueId]/page.tsx", import.meta.url), "utf8");
const awayDayScoreSource = readFileSync(new URL("../app/components/AwayDayScore.tsx", import.meta.url), "utf8");
const globalStylesSource = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

function decisionFixture(overrides: Partial<Fixture>): Fixture {
  return {
    fixture_id: 1,
    fixture_date: "2026-09-10T15:00:00Z",
    home_team: "Home",
    away_team: "Away",
    league_id: 39,
    league_name: "League",
    venue_id: 10,
    venue_name: "Ground",
    venue_city: "City",
    latitude: 51,
    longitude: -1,
    distance_miles: 1,
    status: "NS",
    home_goals: null,
    away_goals: null,
    away_day_score: null,
    atmosphere_score: null,
    review_count: 0,
    recommend_percentage: null,
    open_to_meet_count: 0,
    highlight_eligible: false,
    lead_decision_reason: null,
    ...overrides,
  };
}

test("Discover uses OSM until all Mapbox values are configured", () => {
  assert.equal(discoverTileLayerConfig({}).url, "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png");
  assert.equal(discoverTileLayerConfig({ token: "public-token" }).url, "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png");
  assert.equal(discoverTileLayerConfig({ token: "public-token", username: "map-owner" }).url, "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png");
  assert.equal(discoverTileLayerConfig({ token: "public-token", username: "../unsafe", styleId: "style-id" }).url, "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png");
});

test("Discover accepts a configured Mapbox 512px raster style without changing Leaflet", () => {
  assert.deepEqual(discoverTileLayerConfig({ token: "public token", username: "map-owner", styleId: "style-id" }), {
    url: "https://api.mapbox.com/styles/v1/map-owner/style-id/tiles/512/{z}/{x}/{y}?access_token=public%20token",
    attribution: '<a href="https://www.mapbox.com/about/maps/" target="_blank">&copy; Mapbox</a> <a href="https://www.openstreetmap.org/copyright" target="_blank">&copy; OpenStreetMap contributors</a>',
    crossOrigin: true,
    tileSize: 512,
    zoomOffset: -1,
  });
});

test("grouped marker becomes gold and initially selects the earliest eligible fixture", () => {
  const reason = { key: "CLASSIC_GROUND", emoji: "🧱", label: "Classic ground", explanation: "A historic football setting.", importance: "PRIMARY" };
  const grouped = groupFixturesByVenue([
    decisionFixture({ fixture_id: 3, fixture_date: "2026-09-12T15:00:00Z" }),
    decisionFixture({ fixture_id: 2, fixture_date: "2026-09-11T15:00:00Z", highlight_eligible: true, lead_decision_reason: reason }),
    decisionFixture({ fixture_id: 1, fixture_date: "2026-09-10T15:00:00Z" }),
  ])[0];
  assert.deepEqual(grouped.fixtures.map((fixture) => fixture.fixture_id), [1, 2, 3]);
  assert.deepEqual(fixtureGroupDecision(grouped.fixtures), { highlighted: true, initialFixtureIndex: 1 });
  assert.equal(grouped.fixtures.length, 3, "ordinary fixtures remain navigable in the highlighted group");
});

test("ordinary fixture group and marker/card presentation remain unchanged", () => {
  const fixtures = [decisionFixture({ fixture_id: 1 }), decisionFixture({ fixture_id: 2 })];
  assert.deepEqual(fixtureGroupDecision(fixtures), { highlighted: false, initialFixtureIndex: 0 });
  assert.match(groundMarkerSource, /highlighted \? "#D6A600" : "#2146D0"/);
  assert.match(fixtureCarouselSource, /h-\[18\.5rem\]/);
});

test("Discover popup and carousel expose only the compact lead reason with restrained gold treatment", () => {
  assert.match(fixtureMapSource, /fixture\.lead_decision_reason\.emoji/);
  assert.match(fixtureMapSource, /border-\[var\(--tt-gold\)\]/);
  assert.match(fixtureMapSource, /line-clamp-2 break-words text-sm leading-tight/);
  assert.doesNotMatch(fixtureMapSource, /fixture\.lead_decision_reason\.explanation/);
  assert.match(fixtureCarouselSource, /fixture\.lead_decision_reason\.label/);
  assert.doesNotMatch(fixtureCarouselSource, /fixture\.lead_decision_reason\.explanation/);
  assert.doesNotMatch(fixtureMapSource, /decision_reasons/);
  assert.doesNotMatch(fixtureCarouselSource, /decision_reasons/);
});

test("fixture popup keeps required match details, accessible dismiss, and View match action", () => {
  assert.match(fixtureMapSource, /block min-w-0 break-words leading-tight/);
  assert.match(fixtureMapSource, /fixture\.league_name/);
  assert.match(fixtureMapSource, /fixture\.venue_name/);
  assert.match(fixtureMapSource, /fixture\.distance_miles\.toFixed\(1\)/);
  assert.match(fixtureMapSource, /aria-label="Dismiss selected fixture"/);
  assert.match(fixtureMapSource, /min-h-11 min-w-11/);
  assert.match(fixtureMapSource, /View match/);
  assert.match(fixtureMapSource, /tt-fixture-popup/);
});

test("mobile fixture overlay stays in a control-safe area and preserves core match fields", () => {
  assert.match(globalStylesSource, /\.tt-map \{ height: clamp\(22rem, 58dvh, 25rem\); \}/);
  assert.match(globalStylesSource, /\.tt-mobile-fixture-safe-area \{[\s\S]*bottom: 2rem;[\s\S]*top: 5\.75rem;/);
  assert.match(globalStylesSource, /\.tt-mobile-fixture-card \{[\s\S]*max-width: 100%;[\s\S]*min-width: 0;/);
  assert.match(fixtureMapSource, /tt-mobile-fixture-card/);
  assert.match(fixtureMapSource, /fixture\.home_team} v \{fixture\.away_team/);
  assert.match(fixtureMapSource, /fixture\.fixture_date/);
  assert.match(fixtureMapSource, /fixture\.league_name/);
  assert.match(fixtureMapSource, /fixture\.venue_name/);
  assert.match(fixtureMapSource, /View match/);
  assert.match(fixtureMapSource, /grid-cols-\[minmax\(0,1fr\)_2\.75rem\]/);
  assert.match(fixtureMapSource, /block min-w-0 break-words text-base leading-snug/);
});

test("mobile selection does not own the viewport and dismiss only clears that fixture", () => {
  assert.match(fixtureMapSource, /!compactMobile && <Popup/);
  assert.match(fixtureMapSource, /if \(compactMobile\) \{[\s\S]*onFixtureSelect/);
  assert.match(fixtureMapSource, /popupclose: \(\) => onFixtureDismiss\(fixture\.fixture_id\)/);
  assert.match(fixtureMapSource, /onFixtureDismiss\(fixture\.fixture_id\); map\.closePopup\(\)/);
  assert.match(discoverPageSource, /setSelectedFixtureId\(\(current\) => current === fixtureId \? null : current\)/);
  assert.doesNotMatch(fixtureMapSource, /onFixtureDismiss[\s\S]{0,100}setView/);
});

test("editable mobile controls prevent Safari focus zoom without disabling page zoom", () => {
  assert.match(globalStylesSource, /input\.tt-control,[\s\S]*select\.tt-control,[\s\S]*textarea\.tt-control \{ font-size: 1rem; \}/);
  assert.doesNotMatch(globalStylesSource, /user-scalable|max(?:imum)?-scale/i);
  assert.doesNotMatch(readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8"), /userScalable|maximumScale/);
});

test("Search This Area captures the live viewport before closing selection and never sets a view", () => {
  const areaCapture = fixtureMapSource.indexOf("const area = currentMapArea(mapRef.current)");
  const closeSelection = fixtureMapSource.indexOf("mapRef.current.closePopup()", areaCapture);
  const request = fixtureMapSource.indexOf("await onSearchArea(area)", closeSelection);
  assert.ok(areaCapture > -1 && areaCapture < closeSelection && closeSelection < request);
  const handler = fixtureMapSource.slice(areaCapture, fixtureMapSource.indexOf("setAreaSearchAvailable(false)", request));
  assert.doesNotMatch(handler, /setView|selectedFixture.*latitude|viewportLatitude/);
  assert.match(discoverPageSource, /origin: area\.center/);
  assert.match(discoverPageSource, /latitude: area\.center\.latitude/);
  assert.match(discoverPageSource, /longitude: area\.center\.longitude/);
});

test("opening another marker replaces selection without locking pan or zoom", () => {
  assert.match(fixtureMapSource, /onFixtureSelect\(group\.fixtures\[decision\.initialFixtureIndex\]\.fixture_id\)/);
  assert.match(fixtureMapSource, /useMapEvents\(\{[\s\S]*moveend\(event\)[\s\S]*zoomend\(\)/);
  assert.doesNotMatch(fixtureMapSource, /dragging=\{false\}|scrollWheelZoom=\{false\}|doubleClickZoom=\{false\}/);
});

test("fixture page renders WHY THIS MATCH only when DECIDE reasons exist", () => {
  const match = fixturePageSource.indexOf("01 / Match");
  const why = fixturePageSource.indexOf("02 / Why this match");
  const know = fixturePageSource.indexOf("<FixtureKnow know={know}");
  const matchday = fixturePageSource.indexOf("Ground essentials");
  const social = fixturePageSource.indexOf("/ Social · Did you go?");
  assert.ok(match < why && why < know && know < matchday && matchday < social);
  assert.match(fixturePageSource, /\{hasDecisionReasons && <section/);
  assert.match(fixturePageSource, /decisionReasons\[0\]\.explanation/);
  assert.match(fixturePageSource, /decisionReasons\.slice\(1\)/);
});

test("fixture page keeps one ground route and surfaces only the differentiated before-match signal", () => {
  assert.doesNotMatch(fixturePageSource, /Know before you go/);
  assert.doesNotMatch(fixturePageSource, /Ground guide/);
  assert.doesNotMatch(fixturePageSource, /fixtureGuideActions/);
  assert.equal(fixturePageSource.match(/Explore the ground/g)?.length, 1);
  assert.match(fixturePageSource, /venueGuide\.before_match\.length > 0/);
  assert.match(fixturePageSource, /Before the match · \{venueGuide\.before_match\.length\}/);
});

test("Discover shortlist contains only future interested fixtures and stays compact", () => {
  assert.match(discoverPageSource, /!fixture\.kickoff_passed/);
  assert.match(discoverPageSource, /fixture\.fixture_date/);
  assert.match(discoverPageSource, /<DiscoverShortlist/);
  assert.match(shortlistSource, /Your shortlist/);
  assert.match(shortlistSource, /Matches you&apos;re considering/);
  assert.match(shortlistSource, /View match/);
  assert.match(shortlistSource, /"Removing…" : "Remove"/);
  assert.doesNotMatch(shortlistSource, /lead_decision_reason|open_to_meet|Who&apos;s Going/);
});

test("My Matchdays is confirmation and attended history, never prospective planning", () => {
  assert.match(matchdaysSource, /fixture\.kickoff_passed/);
  assert.match(matchdaysSource, /fixture\.fixture_date/);
  assert.match(matchdaysSource, /setInterval\(\(\) => setMatchdayNow\(new Date\(\)\), 60_000\)/);
  assert.match(matchdaysSource, /Did you go\?/);
  assert.match(matchdaysSource, /Yes, I was there/);
  assert.match(matchdaysSource, /Didn&apos;t go/);
  assert.match(matchdaysSource, /setFixtures\(\(current\) => current\.filter/);
  assert.match(matchdaysSource, /if \(attended && !attendedFixtureIds\.has/);
  assert.match(matchdaysSource, /api\.post\(`\/fixtures\/\$\{fixture\.fixture_id\}\/attendance`\)/);
  assert.match(matchdaysSource, /api\.delete\(`\/fixtures\/\$\{fixture\.fixture_id\}\/interested`\)/);
  assert.match(matchdaysSource, /api\.get\("\/my-grounds"\)/);
  assert.match(matchdaysSource, /Past Matchdays/);
  assert.doesNotMatch(matchdaysSource, /Upcoming|planned|Who&apos;s Going|Open to meeting supporters/);
});

test("My Matchdays uses one empty state and does not preserve non-attendance history", () => {
  assert.match(matchdaysSource, /Your matchday history starts here/);
  assert.match(matchdaysSource, /unresolvedFixtures\.length === 0 && attendedFixtures\.length === 0/);
  assert.equal((matchdaysSource.match(/Your matchday history starts here/g) ?? []).length, 1);
  assert.doesNotMatch(matchdaysSource, /No upcoming plans|No past plans|No attended matches/);
  assert.doesNotMatch(matchdaysSource, /didn.?t attend.*history/i);
});

test("My Grounds filters one coherent visit view and keeps cards supporter-facing", () => {
  assert.match(groundsSource, /groundTimeframes/);
  assert.match(groundsSource, /groundsInTimeframe\(grounds, timeframe\)/);
  assert.match(groundsSource, /PersonalGroundMap grounds=\{visibleGrounds\}/);
  assert.match(groundsSource, /Last there ·/);
  assert.doesNotMatch(groundsSource, />Visits</);
  assert.doesNotMatch(groundsSource, />My rating</);
  assert.doesNotMatch(groundsSource, />Terrace rating</);
  assert.match(groundsSource, /min-h-11 shrink-0 border-b-2/);
  assert.doesNotMatch(groundsSource, /timeframe === option\.key \? "bg-/);
});

test("My Grounds keeps Add a ground secondary and visited dots light but tappable", () => {
  assert.match(groundsSource, /tt-action tt-action-secondary mt-4 inline-flex h-11 items-center justify-center whitespace-nowrap px-4 text-xs">\+ Add a ground/);
  assert.match(groundMarkerSource, /width="14" height="14" viewBox="0 0 14 14"/);
  assert.match(groundMarkerSource, /r="6" fill="#2146D0" stroke="#171717" stroke-width="1\.5"/);
  assert.match(groundMarkerSource, /iconSize: \[VENUE_MARKER_DESIGN\.hitSize, VENUE_MARKER_DESIGN\.hitSize\]/);
  assert.equal(VENUE_MARKER_DESIGN.hitSize, 44);
  assert.match(globalStylesSource, /\.tt-attended-ground-marker__visual \{ display: grid; height: 44px; place-items: center; width: 44px; \}/);
});

test("visits can attach, change, or remove an optional fixture without another model", () => {
  assert.match(groundsSource, /visits\/\$\{visitId\}/);
  assert.match(groundsSource, /fixture_id: fixtureId/);
  assert.match(groundsSource, /Attach match/);
  assert.match(groundsSource, /Change match/);
  assert.match(groundsSource, /Remove link/);
  assert.match(groundsSource, /visit\.visit_date \? knownDate\(visit\.visit_date\) : "Date not remembered"/);
  assert.match(groundsSource, /fixture\.home_team} v \{fixture\.away_team/);
  assert.match(groundsSource, /fixture\.league_name/);
});

test("Ground surfaces approved WHY GO only and suppresses meaningless zero interested counts", () => {
  assert.match(groundPageSource, /decisionReasons\.length > 0/);
  assert.match(groundPageSource, /Why go\?/);
  assert.match(groundPageSource, /fixture\.interested_count > 0/);
});

test("Ground avoids a duplicate empty-rating visit prompt while keeping Your visit and tips", () => {
  assert.doesNotMatch(awayDayScoreSource, /Been here\? Add your take/);
  assert.match(awayDayScoreSource, /if \(!hasReviews\) return null/);
  assert.match(groundPageSource, /03 \/ Your visit/);
  assert.match(groundPageSource, /<MatchdayTips tips=\{tips\}/);
});

test("completed fixture detail relies on its result and past-match context, not a status row", () => {
  assert.match(fixturePageSource, /statusGroup !== "upcoming" && !completed/);
});

test("manual search keeps dates visible before genuinely optional filters and the single Search action", () => {
  const dates = discoverPageSource.indexOf("<DateRangeFields");
  const optionalFilters = discoverPageSource.indexOf("<span>Filters</span>");
  const search = discoverPageSource.indexOf('type="submit"', optionalFilters);
  assert.ok(dates > -1 && dates < optionalFilters);
  assert.ok(optionalFilters < search);
  assert.equal((discoverPageSource.match(/type="submit"/g) ?? []).length, 1);
});

test("unified date picker opens one controlled calendar and selects a range", () => {
  assert.match(searchBarSource, /aria-haspopup="dialog" aria-expanded=\{open\}/);
  assert.match(searchBarSource, /role="dialog" aria-modal="true" aria-label="Choose match dates"/);
  assert.match(searchBarSource, /setDraftStart\(day\)[\s\S]*setChoosingEnd\(true\)/);
  assert.match(searchBarSource, /commit\(draftStart, day\)/);
  assert.match(searchBarSource, /value >= draftStart && value <= draftEnd/);
});

test("untouched Discover defaults to fourteen local calendar days", () => {
  assert.deepEqual(nextFourteenDaysDateRange(new Date(2026, 8, 6, 23, 30)), {
    startDate: "2026-09-06",
    endDate: "2026-09-19",
  });
  assert.match(discoverPageSource, /useState<Date \| null>\(null\)/);
  assert.match(discoverPageSource, /const localNow = new Date\(\)/);
  assert.match(discoverPageSource, /setSelectedStartDate\(\(current\) => current \|\| initialRange\.startDate\)/);
  assert.match(discoverPageSource, /setEndDate\(\(current\) => current \|\| initialRange\.endDate\)/);
  assert.match(discoverPageSource, /const endDate = endDateAtOrAfterStart\(startDate, selectedEndDate\)/);
  assert.match(discoverPageSource, /"Next 14 days" : "Custom dates"/);
});

test("unified date picker supports one day and the four frozen shortcuts", () => {
  assert.match(searchBarSource, /setDraftEnd\(day\)[\s\S]*setChoosingEnd\(true\)/);
  assert.match(searchBarSource, /Tap the same date twice for one day/);
  for (const label of ["Today", "Tomorrow", "This weekend", "Next weekend"]) assert.match(searchBarSource, new RegExp(label));
  assert.match(searchBarSource, /upcomingWeekendDateRange\(now\)/);
  assert.match(searchBarSource, /addCalendarDays\(weekend\.startDate, 7\)/);
});

test("mobile Discover exposes no visible native date inputs", () => {
  assert.doesNotMatch(searchBarSource, /type="date"/);
  assert.doesNotMatch(searchBarSource, /showPicker/);
  assert.match(searchBarSource, /min-h-11/);
});

test("Discover landing keeps the two current-location jobs distinct and removes redundant instruction", () => {
  assert.match(discoverPageSource, /Find football near me this weekend/);
  assert.match(discoverPageSource, /Use my location/);
  assert.match(discoverPageSource, /\n\s+Where\?\n/);
  assert.doesNotMatch(discoverPageSource, /Start here|or search a place|Where do you want to go\?/i);
});

test("successful results collapse to the applied summary and Edit reopens the form", () => {
  assert.match(discoverPageSource, /!editingSearch && appliedSearch/);
  assert.match(discoverPageSource, /appliedSearch\.locationName[\s\S]*appliedDateSummary[\s\S]*All leagues/);
  assert.match(discoverPageSource, /onClick=\{\(\) => setEditingSearch\(true\)\}/);
  assert.match(discoverPageSource, /setEditingSearch\(false\)/);
});

test("mobile filters are bounded inline while desktop retains its dropdown", () => {
  assert.match(searchBarSource, /tt-league-options/);
  assert.match(globalStylesSource, /\.tt-league-options \{ max-height: min\(40dvh, 20rem\); position: relative; width: 100%; \}/);
  assert.match(globalStylesSource, /@media \(min-width: 641px\)[\s\S]*\.tt-league-options \{ max-height: 20rem; position: absolute;/);
});

test("optional filter labels and selected values share a calm hierarchy", () => {
  assert.equal((searchBarSource.match(/text-xs font-bold uppercase tracking-\[0\.1em\] text-\[var\(--tt-muted\)\]/g) ?? []).length, 2);
  assert.equal((searchBarSource.match(/text-\[0\.65rem\] font-medium normal-case tracking-normal">Optional/g) ?? []).length, 2);
  assert.match(searchBarSource, /select value=\{radius\}[\s\S]*font-medium normal-case tracking-normal text-\[var\(--tt-ink\)\]/);
  assert.match(searchBarSource, /summary className="[^"]*font-medium normal-case tracking-normal text-\[var\(--tt-ink\)\]/);
});

test("mobile results retain an intentional carousel teaser and wrap long metadata", () => {
  assert.match(fixtureCarouselSource, /w-\[87%\] min-w-\[87%\] max-w-none/);
  assert.match(fixtureCarouselSource, /snap-x snap-mandatory/);
  assert.match(fixtureCarouselSource, /line-clamp-2 min-w-0 break-words[\s\S]*fixture\.league_name/);
  assert.match(fixtureCarouselSource, /line-clamp-2 min-w-0 break-words[\s\S]*fixture\.venue_name/);
});

test("Discover calendar dates follow the browser timezone across UTC boundaries and DST", () => {
  const originalTimezone = process.env.TZ;
  const localValue = (timezone: string, instant: string) => {
    process.env.TZ = timezone;
    return localCalendarDateValue(new Date(instant));
  };

  try {
    assert.equal(localValue("America/New_York", "2026-09-09T01:27:00Z"), "2026-09-08");
    assert.equal(localValue("America/New_York", "2026-09-09T04:01:00Z"), "2026-09-09");
    assert.equal(localValue("America/Los_Angeles", "2026-09-09T06:30:00Z"), "2026-09-08");
    assert.equal(localValue("Europe/Berlin", "2026-09-08T22:30:00Z"), "2026-09-09");
    assert.equal(localValue("Europe/London", "2026-10-25T00:30:00Z"), "2026-10-25");
    assert.equal(localValue("Europe/London", "2026-10-25T02:30:00Z"), "2026-10-25");
  } finally {
    if (originalTimezone === undefined) delete process.env.TZ;
    else process.env.TZ = originalTimezone;
  }
});

test("weekend shortcut stays on the browser-local week when UTC is already next day", () => {
  const originalTimezone = process.env.TZ;
  process.env.TZ = "America/New_York";
  try {
    assert.deepEqual(upcomingWeekendDateRange(new Date("2026-09-09T01:27:00Z")), {
      startDate: "2026-09-11",
      endDate: "2026-09-13",
    });
  } finally {
    if (originalTimezone === undefined) delete process.env.TZ;
    else process.env.TZ = originalTimezone;
  }
});

test("server render leaves the controlled calendar neutral until client initialization", () => {
  assert.match(discoverPageSource, /const today = discoveryNow \? localCalendarDateValue\(discoveryNow\) : ""/);
  assert.match(discoverPageSource, /const \[selectedStartDate, setSelectedStartDate\] =\s*useState\(""\)/);
  assert.match(discoverPageSource, /className=\{discoveryNow \? "" : "invisible"\}/);
  assert.match(searchBarSource, /disabled = value < minimumStartDate/);
  assert.match(searchBarSource, /monthStart\(startDate \|\| minimumStartDate\)/);
});

test("weekend shortcut selects the upcoming Friday through Sunday on a weekday", () => {
  assert.deepEqual(upcomingWeekendDateRange(new Date(2026, 8, 2, 12)), {
    startDate: "2026-09-04",
    endDate: "2026-09-06",
  });
});

test("weekend shortcut keeps the current Friday through Sunday all weekend", () => {
  assert.deepEqual(upcomingWeekendDateRange(new Date(2026, 8, 4, 12)), {
    startDate: "2026-09-04",
    endDate: "2026-09-06",
  });
  assert.deepEqual(upcomingWeekendDateRange(new Date(2026, 8, 5, 12)), {
    startDate: "2026-09-04",
    endDate: "2026-09-06",
  });
  assert.deepEqual(upcomingWeekendDateRange(new Date(2026, 8, 6, 12)), {
    startDate: "2026-09-04",
    endDate: "2026-09-06",
  });
});

test("manual end date never precedes the chosen start date", () => {
  assert.equal(endDateAtOrAfterStart("2026-12-26", "2026-09-30"), "2026-12-26");
  assert.equal(endDateAtOrAfterStart("2026-12-26", "2026-12-28"), "2026-12-28");
});

test("manual Use my location establishes an origin without choosing dates", () => {
  const origin = { latitude: 53.4106, longitude: -2.1575 };
  assert.deepEqual(manualCurrentLocationOrigin(origin), {
    locationQuery: "Current location",
    draftCoordinates: origin,
    userLocation: origin,
  });
});

test("resolved location immediately builds the viewport discovery request without a movement event", () => {
  const params = buildViewportDiscoveryParams(miamiViewport, {
    startDate: "2026-08-20",
    endDate: "2026-10-01",
    leagueIds: [],
  });

  assert.deepEqual(params, {
    latitude: 25.7741566,
    longitude: -80.1935973,
    north: 26.3241566,
    south: 25.2241566,
    east: -79.4435973,
    west: -80.9435973,
    start_date: "2026-08-20",
    end_date: "2026-10-01",
    league_id: undefined,
    limit: 250,
  });
});

test("location and Search This Area use equivalent requests for equivalent viewport coordinates", () => {
  const filters = {
    startDate: "2026-08-20",
    endDate: "2026-10-01",
    leagueIds: [253, 71],
  };

  assert.deepEqual(
    buildViewportDiscoveryParams({ ...miamiViewport }, filters),
    buildViewportDiscoveryParams({ ...miamiViewport }, filters),
  );
});

test("Search This Area keeps the live map center instead of the previous searched location", () => {
  const previous = { latitude: 25.7741566, longitude: -80.1935973, locationName: "Miami", radius: 25 };
  const liveCenter = { latitude: 25.81, longitude: -80.16 };

  assert.deepEqual(applyMapAreaOrigin(previous, liveCenter), {
    latitude: 25.81,
    longitude: -80.16,
    locationName: "Map area",
    radius: 25,
  });
});

test("viewport requests preserve date and league filters", () => {
  const params = buildViewportDiscoveryParams(miamiViewport, {
    startDate: "2026-08-25",
    endDate: "2026-09-02",
    leagueIds: [253],
    limit: 100,
  });

  assert.equal(params.start_date, "2026-08-25");
  assert.equal(params.end_date, "2026-09-02");
  assert.deepEqual(params.league_id, [253]);
  assert.equal(params.limit, 100);
});

test("only the newest discovery request may apply its result", () => {
  assert.equal(isCurrentDiscoveryRequest(8, 8), true);
  assert.equal(isCurrentDiscoveryRequest(8, 7), false);
});

test("selected radius controls the initial map scale before its viewport is searched", () => {
  assert.equal(discoveryZoomForRadius(10), 10);
  assert.equal(discoveryZoomForRadius(25), 8);
  assert.equal(discoveryZoomForRadius(50), 7);
  assert.equal(discoveryZoomForRadius(100), 6);
});

test("manual city discovery is built from the resolved city viewport", () => {
  const params = buildViewportDiscoveryParams(miamiViewport, {
    startDate: "2026-08-20",
    endDate: "2026-10-01",
    leagueIds: [253],
  });
  assert.equal(params.latitude, miamiViewport.center.latitude);
  assert.equal(params.longitude, miamiViewport.center.longitude);
});

test("Use My Location replaces the previous city target and advances the viewport", () => {
  const currentLocation = { latitude: 51.5074, longitude: -0.1278 };
  const transition = resolvedLocationTransition(currentLocation, "Current location", 12, 4);

  assert.deepEqual(transition, {
    requestVersion: 12,
    locationQuery: "Current location",
    draftCoordinates: currentLocation,
    viewportTarget: { ...currentLocation, revision: 5 },
  });
  assert.notDeepEqual(transition.draftCoordinates, miamiViewport.center);
});

test("current-location bounds replace previous city bounds while preserving filters", () => {
  const londonViewport: DiscoveryViewport = {
    center: { latitude: 51.5074, longitude: -0.1278 },
    north: 51.7,
    south: 51.3,
    east: 0.1,
    west: -0.35,
  };
  const params = buildViewportDiscoveryParams(londonViewport, {
    startDate: "2026-08-25",
    endDate: "2026-09-02",
    leagueIds: [39, 40],
  });

  assert.deepEqual(params, {
    latitude: 51.5074,
    longitude: -0.1278,
    north: 51.7,
    south: 51.3,
    east: 0.1,
    west: -0.35,
    start_date: "2026-08-25",
    end_date: "2026-09-02",
    league_id: [39, 40],
    limit: 250,
  });
});

test("a stale city response cannot overwrite the newer geolocation action", () => {
  assert.equal(isCurrentDiscoveryRequest(12, 11), false);
  assert.equal(isCurrentDiscoveryRequest(12, 12), true);
});

test("Search This Area after geolocation uses the live viewport", () => {
  const geolocationSearch = { latitude: 51.5074, longitude: -0.1278, locationName: "Current location", radius: 25 };
  const liveCenter = { latitude: 51.52, longitude: -0.09 };
  assert.deepEqual(applyMapAreaOrigin(geolocationSearch, liveCenter), {
    latitude: 51.52,
    longitude: -0.09,
    locationName: "Map area",
    radius: 25,
  });
});

test("compact fixture card exposes only matchup, timing source, status and link", () => {
  const fixture = {
    fixture_id: 1561634,
    fixture_date: "2026-08-29T15:00:00Z",
    home_team: "Hutnik Kraków",
    away_team: "Stal Stalowa Wola",
    status: "NS",
    home_goals: null,
    away_goals: null,
    league_id: 109,
    league_name: "II Liga",
    venue_id: 22950,
    venue_name: "Stadion Suche Stawy",
    venue_city: "Kraków",
    latitude: 50.066111,
    longitude: 20.057222,
    distance_miles: 5.38,
    away_day_score: null,
    atmosphere_score: null,
    review_count: 0,
    recommend_percentage: null,
    open_to_meet_count: 0,
    highlight_eligible: false,
    lead_decision_reason: null,
  };

  assert.deepEqual(compactFixtureCard(fixture), {
    matchup: "Hutnik Kraków v Stal Stalowa Wola",
    fixtureDate: "2026-08-29T15:00:00Z",
    status: "NS",
    href: "/fixture/1561634",
  });
});

test("fixture popup auto-pans with padding while preserving normal close behavior", () => {
  assert.deepEqual(FIXTURE_POPUP_BEHAVIOR, {
    autoPan: true,
    autoPanPaddingTopLeft: [56, 72],
    autoPanPaddingBottomRight: [32, 32],
    autoClose: true,
    closeOnClick: true,
  });
});

test("successful geolocation creates and updates the genuine user marker", () => {
  const london = { latitude: 51.5074, longitude: -0.1278 };
  const updated = { latitude: 51.508, longitude: -0.126 };
  assert.deepEqual(applyUserLocationEvent(null, { type: "geolocation", location: london }), london);
  assert.deepEqual(applyUserLocationEvent(london, { type: "geolocation", location: updated }), updated);
});

test("manual location search clears the user marker", () => {
  const london = { latitude: 51.5074, longitude: -0.1278 };
  assert.equal(applyUserLocationEvent(london, { type: "manual-location" }), null);
});

test("map movement cannot move the genuine user marker", () => {
  const london = { latitude: 51.5074, longitude: -0.1278 };
  assert.deepEqual(applyUserLocationEvent(london, { type: "map-moved" }), london);
});

test("venue markers are visually smaller while retaining a usable hit target", () => {
  const marker = venueMarkerPresentation(false, false);
  assert.deepEqual(marker, { visited: false, selected: false, visibleWidth: 24, visibleHeight: 29, hitSize: 44 });
  assert.equal(VENUE_MARKER_DESIGN.hitSize, 44);
  assert.equal(USER_MARKER_DESIGN.visibleSize, 16);
});

test("selected and visited venue marker states remain identifiable", () => {
  const selected = venueMarkerPresentation(false, true);
  const visited = venueMarkerPresentation(true, false);
  const selectedVisited = venueMarkerPresentation(true, true);
  assert.equal(selected.visibleWidth, 28);
  assert.equal(selected.visibleHeight, 34);
  assert.equal(visited.visited, true);
  assert.equal(selectedVisited.visited, true);
  assert.equal(selectedVisited.selected, true);
  assert.equal(selected.hitSize, 44);
});

test("city search to Use My Location invalidates the city target before requesting position", () => {
  assert.deepEqual(beginGeolocationTransition(11), {
    requestVersion: 12,
    draftCoordinates: null,
    viewportTarget: { latitude: 0, longitude: 0, revision: 0 },
  });
});

test("successful geolocation becomes authoritative and produces a new map target", () => {
  const cityTarget = { latitude: 25.774, longitude: -80.194, revision: 4 };
  const started = beginGeolocationTransition(11);
  const position = { latitude: 51.5074, longitude: -0.1278 };
  const resolved = resolvedLocationTransition(position, "Current location", started.requestVersion, cityTarget.revision);

  assert.deepEqual(resolved.viewportTarget, { ...position, revision: 5 });
  assert.deepEqual(resolved.draftCoordinates, position);
  assert.equal(resolved.locationQuery, "Current location");
});

test("failed geolocation clears the pending target without moving the rendered map", () => {
  const started = beginGeolocationTransition(11);
  const existingMarker = { latitude: 51.5074, longitude: -0.1278 };

  assert.equal(started.viewportTarget.revision, 0);
  assert.deepEqual(applyUserLocationEvent(existingMarker, { type: "map-moved" }), existingMarker);
});

test("PERMISSION_DENIED has concise settings guidance", () => {
  assert.equal(
    geolocationErrorMessage(1),
    "Location access is off. Enable location access or search for a city.",
  );
});

test("POSITION_UNAVAILABLE does not claim permission was denied", () => {
  assert.equal(
    geolocationErrorMessage(2),
    "Couldn’t get your location. Try again or search for a city.",
  );
  assert.notEqual(geolocationErrorMessage(2), geolocationErrorMessage(1));
});

test("TIMEOUT does not claim permission was denied", () => {
  assert.equal(
    geolocationErrorMessage(3),
    "Couldn’t get your location. Try again or search for a city.",
  );
  assert.notEqual(geolocationErrorMessage(3), geolocationErrorMessage(1));
});

test("unsupported and insecure-context fallbacks remain distinct", () => {
  assert.equal(GEOLOCATION_UNSUPPORTED_MESSAGE, "Location isn’t available in this browser. Search for a city.");
  assert.equal(GEOLOCATION_INSECURE_MESSAGE, "Use HTTPS for current location, or search for a city.");
});
