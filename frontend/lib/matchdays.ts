import { eligibleAttendanceFixture } from "./attendance-eligibility.ts";
import { formatKickoffTime } from "./fixture-format.ts";


export type ConfirmedGoing<T> = { fixture: T; going: boolean; checked: boolean };

/** Protect a PUT acknowledgement while checking a conflicting read once more.
 * The API has no revision token: a subsequent fresh read must be allowed to
 * reconcile a real reversal/removal rather than pinning client state forever.
 */
export function reconcileGoingRead<T extends { fixture_id: number; going?: boolean }>(
  rows: T[], confirmations: Map<number, ConfirmedGoing<T>>,
) {
  const next = [...rows];
  const retry: number[] = [];
  const changed: number[] = [];
  const confirmed: number[] = [];
  for (const [id, confirmation] of confirmations) {
    const index = next.findIndex(row => row.fixture_id === id);
    if (index >= 0 && next[index].going === confirmation.going) {
      confirmations.delete(id);
      confirmed.push(id);
    } else if (!confirmation.checked) {
      confirmation.checked = true;
      const protectedRow = { ...(index >= 0 ? next[index] : confirmation.fixture), going: confirmation.going };
      if (index >= 0) next[index] = protectedRow; else next.push(protectedRow);
      retry.push(id);
    } else {
      confirmations.delete(id);
      changed.push(id);
    }
  }
  return { rows: next, retry, changed, confirmed };
}

export type ResultFields = {
  status?: string | null;
  home_goals?: number | null;
  away_goals?: number | null;
};

export function trustworthyScore(fixture: ResultFields): string | null {
  const finished = new Set(["FT", "AET", "PEN"]).has((fixture.status ?? "").toUpperCase());
  return finished && fixture.home_goals != null && fixture.away_goals != null
    ? `${fixture.home_goals}–${fixture.away_goals}`
    : null;
}


type SavedMatch = { fixture_id: number; fixture_date: string; status?: string | null; going?: boolean; venue_id?: number | null };
export function canConfirmAttendance(fixture: SavedMatch, now: Date): boolean {
  return fixture.venue_id != null && eligibleAttendanceFixture(fixture, fixture.venue_id, now);
}

export function partitionMatchdays<T extends SavedMatch>(saved: T[], attendedIds: Set<number>, now: Date) {
  const unique = [...new Map(saved.map((fixture) => [fixture.fixture_id, fixture])).values()]
    .filter((fixture) => !attendedIds.has(fixture.fixture_id));
  const awaiting = unique.filter((fixture) => canConfirmAttendance(fixture, now))
    .sort((a, b) => Number(Boolean(b.going)) - Number(Boolean(a.going)) || new Date(b.fixture_date).getTime() - new Date(a.fixture_date).getTime());
  const awaitingIds = new Set(awaiting.map((fixture) => fixture.fixture_id));
  const remaining = unique.filter((fixture) => !awaitingIds.has(fixture.fixture_id))
    .sort((a, b) => new Date(a.fixture_date).getTime() - new Date(b.fixture_date).getTime());
  return { going: remaining.filter((fixture) => fixture.going), interested: remaining.filter((fixture) => !fixture.going), awaiting };
}

/** Display-only; omitted timeZone preserves the browser's current timezone. */
export function formatMatchdayKickoff(value: string, timeZone?: string) {
  const instant = new Date(value);
  return {
    date: new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone }).format(instant).replace(",", ""),
    time: formatKickoffTime(instant, { timeZone }),
  };
}
