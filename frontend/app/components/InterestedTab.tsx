"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiErrorMessage } from "../../lib/api-error";
import api from "../../lib/api";
import { ANSWER_PREVIEW_LIMIT, PAST_PREVIEW_LIMIT, UPCOMING_PREVIEW_LIMIT, previewItems, trustworthyScore } from "../../lib/matchdays";
import type { InterestedFixture } from "../types/interested";
import type { AttendedFixture, MyGround } from "../types/grounds";

type AttendedMatch = AttendedFixture & { venue_id: number; venue_name: string; venue_city: string | null };
type CardFixture = Pick<InterestedFixture, "fixture_id" | "fixture_date" | "home_team" | "away_team"> & Partial<Pick<AttendedFixture, "league_name" | "status" | "home_goals" | "away_goals">>;

const displayDate = (value: string, includeTime = false) => new Date(value).toLocaleDateString(undefined, includeTime
  ? { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }
  : { day: "numeric", month: "short", year: "numeric" });

function MatchdayCard({ fixture, venueName, venueCity, state, footer }: { fixture: CardFixture; venueName: string | null; venueCity: string | null; state: "upcoming" | "answer" | "attended"; footer: ReactNode }) {
  const score = state === "attended" ? trustworthyScore(fixture) : null;
  return <article className={`tt-panel min-w-0 p-4 sm:p-5 ${state === "answer" ? "border-l-4 border-l-[var(--brand-interactive)]" : ""}`}>
    <p className="text-sm font-bold uppercase tracking-[0.08em] text-[var(--tt-muted)]">{displayDate(fixture.fixture_date, state !== "attended")}{fixture.league_name ? ` · ${fixture.league_name}` : ""}</p>
    <Link href={`/fixture/${fixture.fixture_id}`} className="mt-3 grid min-w-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 hover:text-[var(--brand-interactive)]">
      <strong className="min-w-0 break-words text-lg leading-tight">{fixture.home_team}</strong><span className={`font-extrabold ${score ? "text-xl text-[var(--brand-interactive)]" : "text-xs uppercase text-[var(--tt-muted)]"}`}>{score ?? "v"}</span><strong className="min-w-0 break-words text-right text-lg leading-tight">{fixture.away_team}</strong>
    </Link>
    <p className="mt-3 min-w-0 break-words text-base text-[var(--tt-muted)]">{venueName ?? "Ground to be confirmed"}{venueCity ? ` · ${venueCity}` : ""}</p><footer className="mt-3">{footer}</footer>
  </article>;
}

function ExpandButton({ expanded, hiddenCount, onClick, label }: { expanded: boolean; hiddenCount: number; onClick: () => void; label: string }) {
  if (hiddenCount <= 0 && !expanded) return null;
  return <button type="button" onClick={onClick} className="mt-4 min-h-11 text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)] underline decoration-2 underline-offset-4">{expanded ? "Show fewer" : `${label} (${hiddenCount})`}</button>;
}

export default function InterestedTab() {
  const [fixtures, setFixtures] = useState<InterestedFixture[]>([]);
  const [attendedFixtures, setAttendedFixtures] = useState<AttendedMatch[]>([]);
  const [attendanceResolution, setAttendanceResolution] = useState<InterestedFixture | null>(null);
  const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const [updatingFixtureIds, setUpdatingFixtureIds] = useState<number[]>([]); const [matchdayNow, setMatchdayNow] = useState(() => new Date());
  const [showAllUpcoming, setShowAllUpcoming] = useState(false); const [showAllAnswers, setShowAllAnswers] = useState(false); const [showAllPast, setShowAllPast] = useState(false);

  const loadMatchdays = useCallback(() => api.get("/session").then(() => Promise.all([api.get("/interested"), api.get("/my-grounds")])).then(([interestedResponse, groundsResponse]) => {
    const grounds = groundsResponse.data as MyGround[]; setFixtures(interestedResponse.data as InterestedFixture[]);
    setAttendedFixtures(grounds.flatMap((ground) => ground.attended_fixtures.map((fixture) => ({ ...fixture, venue_id: ground.venue_id, venue_name: ground.venue_name, venue_city: ground.venue_city }))).sort((a, b) => new Date(b.fixture_date).getTime() - new Date(a.fixture_date).getTime()));
  }).catch((requestError) => { console.error("My Matchdays loading error:", requestError); setError(apiErrorMessage(requestError, "Unable to establish your Matchgoer session.")); }).finally(() => setLoading(false)), []);

  useEffect(() => { void loadMatchdays(); }, [loadMatchdays]);
  useEffect(() => { const clock = window.setInterval(() => setMatchdayNow(new Date()), 60_000); return () => window.clearInterval(clock); }, []);
  const attendedFixtureIds = useMemo(() => new Set(attendedFixtures.map((fixture) => fixture.fixture_id)), [attendedFixtures]);
  const upcomingFixtures = useMemo(() => fixtures.filter((fixture) => !(fixture.kickoff_passed || new Date(fixture.fixture_date).getTime() <= matchdayNow.getTime())).sort((a, b) => new Date(a.fixture_date).getTime() - new Date(b.fixture_date).getTime()), [fixtures, matchdayNow]);
  const unresolvedFixtures = useMemo(() => fixtures.filter((fixture) => (fixture.kickoff_passed || new Date(fixture.fixture_date).getTime() <= matchdayNow.getTime()) && !attendedFixtureIds.has(fixture.fixture_id)).sort((a, b) => new Date(b.fixture_date).getTime() - new Date(a.fixture_date).getTime()), [attendedFixtureIds, fixtures, matchdayNow]);

  const resolveCompletedFixture = async (fixture: InterestedFixture, attended: boolean) => {
    if (updatingFixtureIds.includes(fixture.fixture_id)) return;
    setUpdatingFixtureIds((current) => [...current, fixture.fixture_id]); setFixtures((current) => current.filter((item) => item.fixture_id !== fixture.fixture_id)); setError("");
    try { if (attended && !attendedFixtureIds.has(fixture.fixture_id)) await api.post(`/fixtures/${fixture.fixture_id}/attendance`); await api.delete(`/fixtures/${fixture.fixture_id}/interested`); if (attended) setAttendanceResolution(fixture); await loadMatchdays(); }
    catch (requestError) { setError(apiErrorMessage(requestError, "Unable to resolve this match.")); await loadMatchdays(); }
    finally { setUpdatingFixtureIds((current) => current.filter((id) => id !== fixture.fixture_id)); }
  };

  const empty = !loading && upcomingFixtures.length === 0 && unresolvedFixtures.length === 0 && attendedFixtures.length === 0;
  const linkFooter = (fixtureId: number) => <Link href={`/fixture/${fixtureId}`} className="inline-flex min-h-11 items-center text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)] underline decoration-2 underline-offset-4">View match →</Link>;

  return <main className="mx-auto max-w-6xl px-4 py-7 sm:px-6 sm:py-10">
    <header className="border-b-[3px] border-[var(--tt-ink)] pb-4"><h1 className="tt-display text-4xl leading-none sm:text-5xl">My Matchdays</h1><p className="mt-2 text-sm text-[var(--tt-muted)]">The occasions you&apos;re looking forward to and the matches you remember.</p><p className="mt-1 text-xs text-[var(--tt-muted)]">Times shown in your current timezone.</p></header>
    {loading && <p className="mt-8 font-semibold text-[var(--tt-muted)]">Loading your matchdays…</p>}{error && <p role="alert" className="mt-6 border-l-4 border-red-700 bg-[var(--tt-paper)] px-4 py-3 font-semibold text-red-800">{error}</p>}{attendanceResolution && <p role="status" className="mt-5 border-l-4 border-[var(--brand-interactive)] px-3 py-2 font-bold">✓ You were there · {attendanceResolution.home_team} v {attendanceResolution.away_team}</p>}
    {empty && <section className="tt-panel mt-7 border-l-[8px] border-l-[var(--brand-interactive)] p-6"><p className="tt-kicker">Your matchday history starts here</p><p className="mt-2 max-w-xl text-sm leading-6 text-[var(--tt-muted)]">Shortlist a fixture, then come back after the match to remember the occasion.</p><Link href="/" className="tt-action mt-5 inline-flex px-5">Find a match →</Link></section>}
    {!loading && upcomingFixtures.length > 0 && <section className="tt-section-rule mt-7 pt-3" aria-labelledby="up-next-heading"><h2 id="up-next-heading" className="tt-display text-3xl leading-none sm:text-4xl">Up Next</h2><p className="mt-1 text-base text-[var(--tt-muted)]">Fixtures you&apos;re interested in.</p><div className="mt-4 grid gap-4 md:grid-cols-2">{previewItems(upcomingFixtures, UPCOMING_PREVIEW_LIMIT, showAllUpcoming).map((fixture) => <MatchdayCard key={fixture.fixture_id} fixture={fixture} venueName={fixture.venue_name} venueCity={fixture.venue_city} state="upcoming" footer={linkFooter(fixture.fixture_id)} />)}</div><ExpandButton expanded={showAllUpcoming} hiddenCount={upcomingFixtures.length - UPCOMING_PREVIEW_LIMIT} onClick={() => setShowAllUpcoming((value) => !value)} label="View all" /></section>}
    {!loading && unresolvedFixtures.length > 0 && <section className="tt-section-rule mt-9 pt-3" aria-labelledby="answer-heading"><h2 id="answer-heading" className="tt-display text-3xl leading-none sm:text-4xl">Did You Go?</h2><p className="mt-1 text-base text-[var(--tt-muted)]">A quick check-in for recently passed fixtures.</p><div className="mt-4 grid gap-4">{previewItems(unresolvedFixtures, ANSWER_PREVIEW_LIMIT, showAllAnswers).map((fixture) => { const updating = updatingFixtureIds.includes(fixture.fixture_id); return <MatchdayCard key={fixture.fixture_id} fixture={fixture} venueName={fixture.venue_name} venueCity={fixture.venue_city} state="answer" footer={<div className="flex flex-wrap items-center gap-x-4"><button type="button" disabled={updating} onClick={() => void resolveCompletedFixture(fixture, true)} className="tt-action px-4">{updating ? "Saving…" : "Yes, I was there"}</button><button type="button" disabled={updating} onClick={() => void resolveCompletedFixture(fixture, false)} className="min-h-11 text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-muted)] underline decoration-2 underline-offset-4">Didn&apos;t go</button></div>} />; })}</div><ExpandButton expanded={showAllAnswers} hiddenCount={unresolvedFixtures.length - ANSWER_PREVIEW_LIMIT} onClick={() => setShowAllAnswers((value) => !value)} label="More to answer" /></section>}
    {!loading && attendedFixtures.length > 0 && <section className="tt-section-rule mt-9 pt-3" aria-labelledby="past-heading"><div className="flex items-end justify-between gap-3"><div><h2 id="past-heading" className="tt-display text-3xl leading-none sm:text-4xl">Past Matchdays</h2><p className="mt-1 text-base text-[var(--tt-muted)]">The football you&apos;ve been to.</p></div><span className="text-sm font-extrabold uppercase tracking-[0.1em] text-[var(--tt-muted)]">{attendedFixtures.length} matches</span></div><div className="mt-5 grid gap-4 md:grid-cols-2">{previewItems(attendedFixtures, PAST_PREVIEW_LIMIT, showAllPast).map((fixture) => <MatchdayCard key={fixture.fixture_id} fixture={fixture} venueName={fixture.venue_name} venueCity={fixture.venue_city} state="attended" footer={linkFooter(fixture.fixture_id)} />)}</div><ExpandButton expanded={showAllPast} hiddenCount={attendedFixtures.length - PAST_PREVIEW_LIMIT} onClick={() => setShowAllPast((value) => !value)} label="View all matchdays" /></section>}
  </main>;
}
