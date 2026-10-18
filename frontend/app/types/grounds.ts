export type ReviewState = "blank" | "partial" | "completed";

export type GroundReview = {
  review_id: number;
  state: ReviewState;
  completed: boolean;
  overall_score: number | null;
  recommend: boolean | null;
  atmosphere_score: number | null;
  pubs_score: number | null;
  getting_there_score: number | null;
  facilities_score: number | null;
};

export type AttendedFixture = {
  home_team_badge_url?: string | null;
  away_team_badge_url?: string | null;
  fixture_id: number;
  fixture_date: string;
  home_team: string;
  away_team: string;
  league_name: string;
  status: string | null;
  home_goals: number | null;
  away_goals: number | null;
};

export type GroundVisit = {
  visit_id: number;
  visit_date: string | null;
  fixture_id: number | null;
};

export type MyGround = {
  venue_id: number;
  venue_name: string;
  venue_city: string | null;
  venue_country: string | null;
  capacity: number | null;
  latitude: number | null;
  longitude: number | null;
  visit_count: number;
  first_visit_date: string | null;
  latest_visit_date: string | null;
  has_undated_visit: boolean;
  visits: GroundVisit[];
  attended_fixtures: AttendedFixture[];
  review: GroundReview | null;
  community_terrace_rating: number | null;
  community_review_count: number;
  community_recommend_percentage: number | null;
};

// Owner-only, bounded current-season projection; no complete league rosters.
export type FootprintCompetition = {
  competition_id: number;
  tier?: number | null;
  season: number;
  season_label: string;
  name: string;
  country: string;
  season_start: string;
  season_end: string;
  coverage: "ready" | "incomplete";
  total_clubs: number;
  lifetime_clubs: number | null;
  season_clubs: number | null;
  grounds: { venue_id: number; clubs: string[]; season_visit_ids: number[] }[];
};
export type FootprintSummary = {
  reviewed_on: string;
  season_visit_ids: number[];
  unclassified_dated_visits: number;
  competitions: FootprintCompetition[];
};
export type MyGroundFootprint = { grounds: MyGround[]; footprint: FootprintSummary };
