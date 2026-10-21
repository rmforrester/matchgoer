import { canRecordCompletedFixture } from "./fixture-status.ts";

// Attendance dates follow the API's canonical UTC calendar, not viewer offsets.
export function isFutureAttendanceDate(value: string, now = new Date()): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && value > now.toISOString().slice(0, 10);
}

export function eligibleAttendanceFixture(fixture: { status?: string | null; fixture_date: string }, venueId: number, now = new Date()): boolean {
  const kickoff = Date.parse(fixture.fixture_date);
  return canRecordCompletedFixture(fixture.status, venueId) && Number.isFinite(kickoff) && kickoff <= now.getTime();
}
