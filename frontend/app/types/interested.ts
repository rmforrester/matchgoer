export type InterestedFixture = {
  interested_id: number;
  fixture_id: number;
  fixture_date: string;
  kickoff_passed: boolean;
  home_team: string;
  away_team: string;
  venue_id: number | null;
  venue_name: string | null;
  venue_city: string | null;
  status: string | null;
  open_to_meet_count: number;
  open_to_meet: boolean;
};
