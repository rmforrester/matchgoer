"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiErrorMessage } from "../../lib/api-error";
import { fixtureStatusGroup, fixtureStatusLabel } from "../../lib/fixture-status";

import api from "../../lib/api";
import AccountConversionPrompt from "./AccountConversionPrompt";
import FixtureTeams from "./FixtureTeams";
import type { AttendedFixture, MyGround, ReviewState } from "../types/grounds";

type InterestedFixture = {
  interested_id: number;
  fixture_id: number;
  fixture_date: string;
  home_team: string;
  away_team: string;
  venue_id: number;
  venue_name: string | null;
  venue_city: string | null;
  status: string | null;
  open_to_meet_count: number;
  open_to_meet: boolean;
};

type AttendedMatch = AttendedFixture & {
  venue_id: number;
  venue_name: string;
  venue_city: string | null;
};

const displayDate = (value: string, includeTime = false) => new Date(value).toLocaleDateString(
  undefined,
  includeTime
    ? { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }
    : { day: "numeric", month: "short", year: "numeric" },
);

function MatchdayCard({
  fixture,
  venueName,
  venueCity,
  includeKickoff = false,
  state,
  footer,
}: {
  fixture: Pick<InterestedFixture, "fixture_id" | "fixture_date" | "home_team" | "away_team"> & { status?: string | null };
  venueName: string | null;
  venueCity: string | null;
  includeKickoff?: boolean;
  state: "upcoming" | "answer" | "attended";
  footer: ReactNode;
}) {
  const statusGroup = fixtureStatusGroup(fixture.status);
  const stateClass = state === "upcoming"
    ? "border-t-[5px] border-t-[var(--tt-blue)]"
    : state === "answer"
      ? "border-l-[5px] border-l-[var(--tt-ink)]"
      : "border-t-[5px] border-t-[var(--tt-rule)]";
  return (
    <article className={`tt-panel flex min-w-0 flex-col p-3.5 sm:p-4 ${stateClass}`}>
      <p className="tt-kicker">{statusGroup === "postponed" || statusGroup === "cancelled" ? fixtureStatusLabel(fixture.status) : displayDate(fixture.fixture_date, includeKickoff)}</p>
      <Link href={`/fixture/${fixture.fixture_id}`} className="mt-2 block min-w-0 hover:text-[var(--tt-blue)]">
        <FixtureTeams
          homeTeam={fixture.home_team}
          awayTeam={fixture.away_team}
          teamClassName="text-[clamp(1.5rem,7vw,2rem)] leading-[0.92] sm:text-[2rem]"
          separatorClassName="my-0.5 text-[0.65rem] tracking-[0.16em]"
        />
      </Link>
      <div className="mt-3 min-w-0 border-t border-[var(--tt-rule)] pt-2.5">
        <p className="truncate text-sm font-extrabold uppercase tracking-[0.06em]">{venueName ?? "Ground to be confirmed"}</p>
        {venueCity && <p className="mt-1 truncate text-xs font-semibold uppercase tracking-[0.08em] text-[var(--tt-muted)]">{venueCity}</p>}
      </div>
      <footer className="mt-3 border-t border-[var(--tt-ink)] pt-3">{footer}</footer>
    </article>
  );
}

function FollowUpActions({ venueId, reviewState }: { venueId: number; reviewState: ReviewState | null }) {
  return (
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs font-extrabold uppercase tracking-[0.08em]">
      <Link href={`/my-football?tab=visited&review=${venueId}`} className="min-h-11 content-center text-[var(--tt-blue)] underline decoration-2 underline-offset-4">
        {reviewState === "completed" ? "Edit my review →" : reviewState === "partial" ? "Continue review →" : "Rate the ground →"}
      </Link>
      <Link href={`/venue/${venueId}#tips-add`} className="min-h-11 content-center text-[var(--tt-blue)] underline decoration-2 underline-offset-4">Add a tip →</Link>
    </div>
  );
}

function EmptySection({ children }: { children: ReactNode }) {
  return <div className="mt-5 border-y-2 border-[var(--tt-ink)] py-5"><p className="tt-display text-2xl text-[var(--tt-muted)]">{children}</p></div>;
}

export default function InterestedTab() {
  const [fixtures, setFixtures] = useState<InterestedFixture[]>([]);
  const [attendedFixtures, setAttendedFixtures] = useState<AttendedMatch[]>([]);
  const [groundReviewStates, setGroundReviewStates] = useState<Record<number, ReviewState | null>>({});
  const [attendanceResolution, setAttendanceResolution] = useState<InterestedFixture | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isAnonymous, setIsAnonymous] = useState(true);
  const [showMatePrompt, setShowMatePrompt] = useState(false);
  const [updatingFixtureIds, setUpdatingFixtureIds] = useState<number[]>([]);

  const loadMatchdays = useCallback(() => api.get("/session")
    .then((sessionResponse) => {
      setIsAnonymous(sessionResponse.data.anonymous !== false);
      return Promise.all([api.get("/interested"), api.get("/my-grounds")]);
    })
    .then(([interestedResponse, groundsResponse]) => {
      const grounds = groundsResponse.data as MyGround[];
      setFixtures(interestedResponse.data);
      setAttendedFixtures(grounds
        .flatMap((ground) => ground.attended_fixtures.map((fixture) => ({
          ...fixture,
          venue_id: ground.venue_id,
          venue_name: ground.venue_name,
          venue_city: ground.venue_city,
        })))
        .sort((left, right) => new Date(right.fixture_date).getTime() - new Date(left.fixture_date).getTime()));
      setGroundReviewStates(Object.fromEntries(grounds.map((ground) => [ground.venue_id, ground.review?.state ?? null])));
    })
    .catch((requestError) => {
      console.error("My Matchdays loading error:", requestError);
      setError(apiErrorMessage(requestError, "Unable to establish your Terrace Talk session."));
    })
    .finally(() => setLoading(false)), []);

  useEffect(() => {
    void loadMatchdays();
  }, [loadMatchdays]);

  const attendedFixtureIds = useMemo(() => new Set(attendedFixtures.map((fixture) => fixture.fixture_id)), [attendedFixtures]);
  const upcomingFixtures = useMemo(() => fixtures
    .filter((fixture) => fixtureStatusGroup(fixture.status) !== "finished")
    .sort((left, right) => new Date(left.fixture_date).getTime() - new Date(right.fixture_date).getTime()), [fixtures]);
  const unresolvedFixtures = useMemo(() => fixtures
    .filter((fixture) => fixtureStatusGroup(fixture.status) === "finished" && !attendedFixtureIds.has(fixture.fixture_id))
    .sort((left, right) => new Date(right.fixture_date).getTime() - new Date(left.fixture_date).getTime()), [attendedFixtureIds, fixtures]);

  const beginUpdate = (fixtureId: number) => {
    if (updatingFixtureIds.includes(fixtureId)) return false;
    setUpdatingFixtureIds((current) => [...current, fixtureId]);
    return true;
  };
  const endUpdate = (fixtureId: number) => setUpdatingFixtureIds((current) => current.filter((id) => id !== fixtureId));

  const removeInterested = (fixtureId: number) => {
    if (!beginUpdate(fixtureId)) return;
    setError("");
    api.delete(`/fixtures/${fixtureId}/interested`)
      .then(() => setFixtures((current) => current.filter((fixture) => fixture.fixture_id !== fixtureId)))
      .catch((requestError) => setError(apiErrorMessage(requestError, "Unable to remove this match from Interested.")))
      .finally(() => endUpdate(fixtureId));
  };

  const toggleMeeting = (fixture: InterestedFixture) => {
    if (updatingFixtureIds.includes(fixture.fixture_id)) return;
    if (isAnonymous && !fixture.open_to_meet) {
      setShowMatePrompt(true);
      return;
    }
    if (!beginUpdate(fixture.fixture_id)) return;
    setError("");
    api.put(`/fixtures/${fixture.fixture_id}/open-to-meet`, { open_to_meet: !fixture.open_to_meet })
      .then((response) => setFixtures((current) => current.map((item) => item.fixture_id === fixture.fixture_id ? {
        ...item,
        open_to_meet: response.data.open_to_meet,
        open_to_meet_count: response.data.open_to_meet_count,
      } : item)))
      .catch((requestError) => setError(apiErrorMessage(requestError, "Unable to update Who's Going?.")))
      .finally(() => endUpdate(fixture.fixture_id));
  };

  const resolveCompletedFixture = async (fixture: InterestedFixture, attended: boolean) => {
    if (!beginUpdate(fixture.fixture_id)) return;
    setError("");
    try {
      if (attended && !attendedFixtureIds.has(fixture.fixture_id)) await api.post(`/fixtures/${fixture.fixture_id}/attendance`);
      await api.delete(`/fixtures/${fixture.fixture_id}/interested`);
      if (attended) setAttendanceResolution(fixture);
      await loadMatchdays();
    } catch (requestError) {
      setError(apiErrorMessage(requestError, "Unable to resolve this match."));
    } finally {
      endUpdate(fixture.fixture_id);
    }
  };

  return (
    <main className="mx-auto max-w-6xl px-4 py-7 sm:px-6 sm:py-10">
      <AccountConversionPrompt open={showMatePrompt} kind="mate" onDismiss={() => setShowMatePrompt(false)} />

      <header className="border-b-[3px] border-[var(--tt-ink)] pb-4">
        <h1 className="tt-display text-4xl leading-none sm:text-5xl">My Matchdays</h1>
        <p className="mt-2 text-xs font-extrabold uppercase tracking-[0.1em] text-[var(--tt-blue)]">{upcomingFixtures.length} upcoming · {attendedFixtures.length} attended</p>
      </header>

      {loading && <p className="mt-8 font-semibold text-[var(--tt-muted)]">Loading your matchdays…</p>}
      {error && <p role="alert" className="mt-6 border-l-4 border-red-700 bg-[var(--tt-paper)] px-4 py-3 font-semibold text-red-800">{error}</p>}

      {attendanceResolution && <aside role="status" className="tt-panel mt-6 border-l-[8px] border-l-[var(--tt-blue)] p-5"><p className="tt-kicker">Attendance recorded</p><FixtureTeams homeTeam={attendanceResolution.home_team} awayTeam={attendanceResolution.away_team} className="mt-2" teamClassName="text-3xl leading-none" separatorClassName="my-1 text-xs tracking-[0.16em]"/><p className="mt-3 text-sm text-[var(--tt-muted)]">This match is now under Attended and the ground is in My Grounds. A review or tip is optional.</p><FollowUpActions venueId={attendanceResolution.venue_id} reviewState={groundReviewStates[attendanceResolution.venue_id]}/></aside>}

      {!loading && <>
        <section className="tt-section-rule mt-7 pt-3" aria-labelledby="upcoming-heading">
          <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 id="upcoming-heading" className="tt-display text-3xl leading-none sm:text-4xl">Upcoming</h2><p className="mt-1 text-sm text-[var(--tt-muted)]">Matches you&apos;re considering.</p></div><span className="text-xs font-extrabold uppercase tracking-[0.1em] text-[var(--tt-blue)]">{upcomingFixtures.length} planned</span></div>
          {upcomingFixtures.length === 0 ? <EmptySection>No upcoming plans yet.</EmptySection> : <div className="mt-5 grid gap-4 md:grid-cols-2">{upcomingFixtures.map((fixture) => {
            const updating = updatingFixtureIds.includes(fixture.fixture_id);
            return <MatchdayCard key={fixture.fixture_id} fixture={fixture} venueName={fixture.venue_name} venueCity={fixture.venue_city} includeKickoff state="upcoming" footer={<><div className="flex flex-wrap items-center justify-between gap-2"><span className="text-xs font-extrabold uppercase tracking-[0.12em] text-[var(--tt-blue)]">✓ Interested</span>{fixture.open_to_meet_count > 0 && <span className="text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-muted)]">Who&apos;s Going? · {fixture.open_to_meet_count}</span>}</div><div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1"><button type="button" disabled={updating} onClick={() => toggleMeeting(fixture)} aria-pressed={fixture.open_to_meet} className={`tt-action px-3 ${fixture.open_to_meet ? "" : "tt-action-secondary"}`}>{updating ? "Saving…" : fixture.open_to_meet ? "✓ Open to meeting supporters" : "Who's Going?"}</button><button type="button" disabled={updating} onClick={() => removeInterested(fixture.fixture_id)} className="min-h-11 text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-muted)] underline decoration-2 underline-offset-4">Remove</button></div></>} />;
          })}</div>}
        </section>

        <section className="tt-section-rule mt-9 pt-3" aria-labelledby="answer-heading">
          <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 id="answer-heading" className="tt-display text-3xl leading-none sm:text-4xl">Did you go?</h2><p className="mt-1 text-sm text-[var(--tt-muted)]">Tell us which games you made it to.</p></div>{unresolvedFixtures.length > 0 && <span className="bg-[var(--tt-ink)] px-2 py-1 text-xs font-extrabold uppercase tracking-[0.1em] text-[var(--tt-paper)]">{unresolvedFixtures.length} {unresolvedFixtures.length === 1 ? "match" : "matches"}</span>}</div>
          {unresolvedFixtures.length === 0 ? <EmptySection>No past plans to check.</EmptySection> : <div className="mt-5 grid gap-4 md:grid-cols-2">{unresolvedFixtures.map((fixture) => {
            const updating = updatingFixtureIds.includes(fixture.fixture_id);
            return <MatchdayCard key={fixture.fixture_id} fixture={fixture} venueName={fixture.venue_name} venueCity={fixture.venue_city} state="answer" footer={<><p className="tt-display text-xl">Did you go?</p><div className="mt-2 grid gap-2 sm:grid-cols-2"><button type="button" disabled={updating} onClick={() => void resolveCompletedFixture(fixture, true)} className="tt-action px-3">{updating ? "Saving…" : "I went to this game"}</button><button type="button" disabled={updating} onClick={() => void resolveCompletedFixture(fixture, false)} className="tt-action tt-action-secondary px-3">I didn&apos;t go</button></div></>} />;
          })}</div>}
        </section>

        <section className="tt-section-rule mt-9 pt-3" aria-labelledby="attended-heading">
          <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 id="attended-heading" className="tt-display text-3xl leading-none sm:text-4xl">Attended</h2><p className="mt-1 text-sm text-[var(--tt-muted)]">The games you&apos;ve been to.</p></div><span className="text-xs font-extrabold uppercase tracking-[0.1em] text-[var(--tt-muted)]">{attendedFixtures.length} matches</span></div>
          {attendedFixtures.length === 0 ? <EmptySection>No attended matches recorded yet.</EmptySection> : <div className="mt-5 grid gap-4 md:grid-cols-2">{attendedFixtures.map((fixture) => <MatchdayCard key={fixture.fixture_id} fixture={fixture} venueName={fixture.venue_name} venueCity={fixture.venue_city} state="attended" footer={<><p className="text-xs font-extrabold uppercase tracking-[0.12em] text-[var(--tt-muted)]">✓ Attended</p><FollowUpActions venueId={fixture.venue_id} reviewState={groundReviewStates[fixture.venue_id]}/></>} />)}</div>}
        </section>

      </>}
    </main>
  );
}
