import { canRecordCompletedFixture } from "./fixture-status.ts";

// Native date inputs use the supporter's local calendar, including near UTC midnight.
export function localAttendanceToday(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}
export function isFutureAttendanceDate(value: string, now = new Date()): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && value > localAttendanceToday(now);
}

export function eligibleAttendanceFixture(fixture: { status?: string | null; fixture_date: string }, venueId: number, now = new Date()): boolean {
  const kickoff = Date.parse(fixture.fixture_date);
  return canRecordCompletedFixture(fixture.status, venueId) && Number.isFinite(kickoff) && kickoff <= now.getTime();
}
