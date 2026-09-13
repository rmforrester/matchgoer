"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiErrorMessage } from "../../lib/api-error";
import api from "../../lib/api";
import type { InterestedFixture } from "../types/interested";
import type { AttendedFixture, MyGround } from "../types/grounds";

type AttendedMatch = AttendedFixture & { venue_id: number; venue_name: string; venue_city: string | null };

const displayDate = (value: string, includeTime = false) => new Date(value).toLocaleDateString(undefined, includeTime
  ? { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }
  : { day: "numeric", month: "short", year: "numeric" });

function MatchdayCard({ fixture, venueName, venueCity, state, footer }: {
  fixture: Pick<InterestedFixture, "fixture_id" | "fixture_date" | "home_team" | "away_team">;
  venueName: string | null;
  venueCity: string | null;
  state: "answer" | "attended";
  footer: ReactNode;
}) {
  return <article className={`min-w-0 border-b-2 border-[var(--tt-ink)] py-3 ${state === "answer" ? "border-l-4 border-l-[var(--brand-interactive)] pl-3" : ""}`}>
    <p className="text-xs font-bold uppercase tracking-[0.08em] text-[var(--tt-muted)]">{displayDate(fixture.fixture_date, state === "answer")}</p>
    <Link href={`/fixture/${fixture.fixture_id}`} className="mt-1 block min-w-0 break-words font-extrabold hover:text-[var(--brand-interactive)]">{fixture.home_team} v {fixture.away_team}</Link>
    <p className="mt-1 min-w-0 break-words text-sm text-[var(--tt-muted)]">{venueName ?? "Ground to be confirmed"}{venueCity ? ` · ${venueCity}` : ""}</p>
    <footer className="mt-2">{footer}</footer>
  </article>;
}

export default function InterestedTab() {
  const [fixtures, setFixtures] = useState<InterestedFixture[]>([]);
  const [attendedFixtures, setAttendedFixtures] = useState<AttendedMatch[]>([]);
  const [attendanceResolution, setAttendanceResolution] = useState<InterestedFixture | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updatingFixtureIds, setUpdatingFixtureIds] = useState<number[]>([]);
  const [matchdayNow, setMatchdayNow] = useState(() => new Date());

  const loadMatchdays = useCallback(() => api.get("/session")
    .then(() => Promise.all([api.get("/interested"), api.get("/my-grounds")]))
    .then(([interestedResponse, groundsResponse]) => {
      const grounds = groundsResponse.data as MyGround[];
      setFixtures(interestedResponse.data as InterestedFixture[]);
      setAttendedFixtures(grounds.flatMap((ground) => ground.attended_fixtures.map((fixture) => ({ ...fixture, venue_id: ground.venue_id, venue_name: ground.venue_name, venue_city: ground.venue_city }))).sort((left, right) => new Date(right.fixture_date).getTime() - new Date(left.fixture_date).getTime()));
    })
    .catch((requestError) => { console.error("My Matchdays loading error:", requestError); setError(apiErrorMessage(requestError, "Unable to establish your Matchgoer session.")); })
    .finally(() => setLoading(false)), []);

  useEffect(() => { void loadMatchdays(); }, [loadMatchdays]);
  useEffect(() => {
    const clock = window.setInterval(() => setMatchdayNow(new Date()), 60_000);
    return () => window.clearInterval(clock);
  }, []);

  const attendedFixtureIds = useMemo(() => new Set(attendedFixtures.map((fixture) => fixture.fixture_id)), [attendedFixtures]);
  const unresolvedFixtures = useMemo(() => fixtures.filter((fixture) => (fixture.kickoff_passed || new Date(fixture.fixture_date).getTime() <= matchdayNow.getTime()) && !attendedFixtureIds.has(fixture.fixture_id)).sort((left, right) => new Date(right.fixture_date).getTime() - new Date(left.fixture_date).getTime()), [attendedFixtureIds, fixtures, matchdayNow]);

  const resolveCompletedFixture = async (fixture: InterestedFixture, attended: boolean) => {
    if (updatingFixtureIds.includes(fixture.fixture_id)) return;
    setUpdatingFixtureIds((current) => [...current, fixture.fixture_id]);
    setFixtures((current) => current.filter((item) => item.fixture_id !== fixture.fixture_id));
    setError("");
    try {
      if (attended && !attendedFixtureIds.has(fixture.fixture_id)) await api.post(`/fixtures/${fixture.fixture_id}/attendance`);
      await api.delete(`/fixtures/${fixture.fixture_id}/interested`);
      if (attended) setAttendanceResolution(fixture);
      await loadMatchdays();
    } catch (requestError) {
      setError(apiErrorMessage(requestError, "Unable to resolve this match."));
      await loadMatchdays();
    } finally {
      setUpdatingFixtureIds((current) => current.filter((id) => id !== fixture.fixture_id));
    }
  };

  const empty = !loading && unresolvedFixtures.length === 0 && attendedFixtures.length === 0;

  return <main className="mx-auto max-w-6xl px-4 py-7 sm:px-6 sm:py-10">
    <header className="border-b-[3px] border-[var(--tt-ink)] pb-4"><h1 className="tt-display text-4xl leading-none sm:text-5xl">My Matchdays</h1><p className="mt-2 text-sm text-[var(--tt-muted)]">The matches you&apos;ve been to.</p><p className="mt-1 text-xs text-[var(--tt-muted)]">Times shown in your current timezone.</p></header>
    {loading && <p className="mt-8 font-semibold text-[var(--tt-muted)]">Loading your matchdays…</p>}
    {error && <p role="alert" className="mt-6 border-l-4 border-red-700 bg-[var(--tt-paper)] px-4 py-3 font-semibold text-red-800">{error}</p>}
    {attendanceResolution && <p role="status" className="mt-5 border-l-4 border-[var(--brand-interactive)] px-3 py-2 font-bold">✓ You were there · {attendanceResolution.home_team} v {attendanceResolution.away_team}</p>}

    {empty && <section className="tt-panel mt-7 border-l-[8px] border-l-[var(--brand-interactive)] p-6"><p className="tt-kicker">Your matchday history starts here</p><p className="mt-2 max-w-xl text-sm leading-6 text-[var(--tt-muted)]">When you attend a match you&apos;ve shortlisted, confirm it here and we&apos;ll build your matchday history.</p><Link href="/" className="tt-action mt-5 inline-flex px-5">Find a match →</Link></section>}

    {!loading && unresolvedFixtures.length > 0 && <section className="tt-section-rule mt-7 pt-3" aria-labelledby="answer-heading"><h2 id="answer-heading" className="tt-display text-3xl leading-none sm:text-4xl">Did you go?</h2><div className="mt-3">{unresolvedFixtures.map((fixture) => {
      const updating = updatingFixtureIds.includes(fixture.fixture_id);
      return <MatchdayCard key={fixture.fixture_id} fixture={fixture} venueName={fixture.venue_name} venueCity={fixture.venue_city} state="answer" footer={<div className="flex flex-wrap items-center gap-x-4"><button type="button" disabled={updating} onClick={() => void resolveCompletedFixture(fixture, true)} className="tt-action px-4">{updating ? "Saving…" : "Yes, I was there"}</button><button type="button" disabled={updating} onClick={() => void resolveCompletedFixture(fixture, false)} className="min-h-11 text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-muted)] underline decoration-2 underline-offset-4">Didn&apos;t go</button></div>} />;
    })}</div></section>}

    {!loading && attendedFixtures.length > 0 && <section className="tt-section-rule mt-9 pt-3" aria-labelledby="past-heading"><div className="flex items-end justify-between gap-3"><div><h2 id="past-heading" className="tt-display text-3xl leading-none sm:text-4xl">Past Matchdays</h2><p className="mt-1 text-sm text-[var(--tt-muted)]">The football you&apos;ve been to.</p></div><span className="text-xs font-extrabold uppercase tracking-[0.1em] text-[var(--tt-muted)]">{attendedFixtures.length} matches</span></div><div className="mt-5 grid gap-4 md:grid-cols-2">{attendedFixtures.map((fixture) => <MatchdayCard key={fixture.fixture_id} fixture={fixture} venueName={fixture.venue_name} venueCity={fixture.venue_city} state="attended" footer={<Link href={`/fixture/${fixture.fixture_id}`} className="min-h-11 content-center text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)] underline decoration-2 underline-offset-4">View match →</Link>} />)}</div></section>}
  </main>;
}
