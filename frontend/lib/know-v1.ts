export type KnowProvenance = { source_type: string; source_title: string; source_url: string | null; source_date: string | null };
export type KnowFact = { know_fact_id: number; headline: string | null; content: string; provenance: KnowProvenance[] };
export type KnowBeforeMatchSpot = {
  pre_match_spot_id: number; display_name: string;
  classification: "SUPPORTER_SPOT" | "CLUB_MATCHDAY_VENUE" | "SUPPORTER_AREA";
  audience: "HOME" | "MIXED"; supporting_line: string | null;
  location_context: string | null; directions_url: string | null;
};
export type FixtureKnow = {
  fixture_id: number; team_id: number | null; venue_id: number | null; club_venue_id: number | null;
  club: KnowFact[]; supporters: KnowFact[]; matchday: KnowFact[]; dont_miss: KnowFact[];
  before_match: KnowBeforeMatchSpot[]; good_to_know: KnowFact[];
};
export function hasKnowContent(know: FixtureKnow | null) {
  return Boolean(know && (know.club.length || know.supporters.length || know.matchday.length || know.dont_miss.length || know.before_match.length || know.good_to_know.length));
}
