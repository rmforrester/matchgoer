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
  fixture_id: number;
  fixture_date: string;
  home_team: string;
  away_team: string;
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
  attended_fixtures: AttendedFixture[];
  review: GroundReview | null;
  community_terrace_rating: number | null;
  community_review_count: number;
  community_recommend_percentage: number | null;
};
