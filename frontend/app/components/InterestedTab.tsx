"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { apiErrorMessage } from "../../lib/api-error";
import api, { apiAssetUrl } from "../../lib/api";
import FixtureTeams from "./FixtureTeams";
import { useAuth } from "./AuthProvider";
import TerracePhotoSubmission from "./TerracePhotoSubmission";
import { recordedPhotoAttendance, type PhotoAttendance } from "../../lib/terraces";
import { trackEvent } from "../../lib/analytics";
import { ANSWER_PREVIEW_LIMIT, PAST_PREVIEW_LIMIT, UPCOMING_PREVIEW_LIMIT, previewItems, trustworthyScore, partitionMatchdays, formatMatchdayKickoff, reconcileGoingRead, type ConfirmedGoing } from "../../lib/matchdays";
import type { InterestedFixture } from "../types/interested";
import type { AttendedFixture, MyGround } from "../types/grounds";

type AttendedMatch = AttendedFixture & { venue_id: number; venue_name: string; venue_city: string | null };
type CardFixture = Pick<InterestedFixture, "fixture_id" | "fixture_date" | "home_team" | "away_team" | "home_team_badge_url" | "away_team_badge_url"> & Partial<Pick<AttendedFixture, "league_name" | "status" | "home_goals" | "away_goals">>;

const displayDate = (value: string, includeTime = false) => new Date(value).toLocaleDateString(undefined, includeTime
  ? { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true }
  : { day: "numeric", month: "short", year: "numeric" });

function MatchdayCard({ fixture, venueName, venueCity, state, footer }: { fixture: CardFixture; venueName: string | null; venueCity: string | null; state: "upcoming" | "answer" | "attended"; footer: ReactNode }) {
  const score = state === "attended" ? trustworthyScore(fixture) : null;
  const kickoff = formatMatchdayKickoff(fixture.fixture_date);
  return <article className={`tt-panel min-w-0 p-4 sm:p-5 ${state === "answer" ? "border-l-4 border-l-[var(--brand-interactive)]" : ""}`}>
    <p className="text-sm font-bold uppercase tracking-[0.08em] text-[var(--tt-muted)]">{state === "attended" ? displayDate(fixture.fixture_date) : <span className="inline-flex flex-wrap items-baseline gap-x-1"><span className="whitespace-nowrap">{kickoff.date}</span><span className="whitespace-nowrap">· {kickoff.time}</span></span>}{fixture.league_name ? <span className="mt-1 block">{fixture.league_name}</span> : null}</p>
    <Link href={`/fixture/${fixture.fixture_id}`} className="mt-3 block min-w-0 hover:text-[var(--brand-interactive)]">
      <FixtureTeams compact homeTeam={fixture.home_team} awayTeam={fixture.away_team} homeBadgeSrc={apiAssetUrl(fixture.home_team_badge_url)} awayBadgeSrc={apiAssetUrl(fixture.away_team_badge_url)} teamClassName="text-xl leading-tight sm:text-2xl" separatorClassName="text-xs" />
      {score && <p className="mt-2 text-center font-extrabold text-[var(--brand-interactive)]">{score}</p>}
    </Link>
    {state !== "attended" && <p className="mt-2 text-xs font-bold uppercase text-[var(--tt-muted)]">{fixture.status === "PST" ? "Postponed - plan retained" : ["CANC", "ABD", "AWD", "WO"].includes(fixture.status ?? "") ? "Not played - plan retained" : ""}</p>}
    <p className="mt-3 min-w-0 break-words text-base text-[var(--tt-muted)]">{venueName ?? "Ground to be confirmed"}{venueCity ? ` · ${venueCity}` : ""}</p><footer className="mt-2">{footer}</footer>
  </article>;
}

function ExpandButton({ expanded, hiddenCount, onClick, label }: { expanded: boolean; hiddenCount: number; onClick: () => void; label: string }) {
  if (hiddenCount <= 0 && !expanded) return null;
  return <button type="button" onClick={onClick} className="mt-4 min-h-11 text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)] underline decoration-2 underline-offset-4">{expanded ? "Show fewer" : `${label} (${hiddenCount})`}</button>;
}

export default function InterestedTab() {
  const { email } = useAuth();
  const [photoAttendances, setPhotoAttendances] = useState<PhotoAttendance[]>([]);
  const [fixtures, setFixtures] = useState<InterestedFixture[]>([]);
  const [attendedFixtures, setAttendedFixtures] = useState<AttendedMatch[]>([]);
  const [attendanceResolution, setAttendanceResolution] = useState<InterestedFixture | null>(null);
  const [planFeedback, setPlanFeedback] = useState<Record<number, { error: boolean; message: string; expectedGoing?: boolean }>>({});
  const requestGeneration = useRef(0);
  const confirmedGoing = useRef(new Map<number, ConfirmedGoing<InterestedFixture>>());
  const savingGoing = useRef(new Set<number>());
  const focusFixture = useRef<number | null>(null);
  const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const [updatingFixtureIds, setUpdatingFixtureIds] = useState<number[]>([]); const [matchdayNow, setMatchdayNow] = useState(() => new Date());
  const [showAllUpcoming, setShowAllUpcoming] = useState(false); const [showAllInterested, setShowAllInterested] = useState(false); const [showAllAnswers, setShowAllAnswers] = useState(false); const [showAllPast, setShowAllPast] = useState(false);

  const loadMatchdays = useCallback(async () => {
    // One bounded retry; overlapping/older loads cannot replace newer state.
    for (let attempt = 0; attempt < 2; attempt++) {
      const generation = ++requestGeneration.current;
      try {
        await api.get("/session");
        const [interestedResponse, groundsResponse] = await Promise.all([api.get("/interested"), api.get("/my-grounds")]);
        if (generation !== requestGeneration.current) return;
        const grounds = groundsResponse.data as MyGround[];
        setPhotoAttendances(recordedPhotoAttendance(grounds));
        const reconciliation = reconcileGoingRead(interestedResponse.data as InterestedFixture[], confirmedGoing.current);
        setFixtures(reconciliation.rows);
        setAttendedFixtures(grounds.flatMap((ground) => ground.attended_fixtures.map((fixture) => ({ ...fixture, venue_id: ground.venue_id, venue_name: ground.venue_name, venue_city: ground.venue_city }))).sort((a, b) => new Date(b.fixture_date).getTime() - new Date(a.fixture_date).getTime()));
        setPlanFeedback(current => {
          const next = { ...current };
          for (const row of reconciliation.rows) {
            const previous = next[row.fixture_id];
            if (previous?.expectedGoing !== undefined && previous.expectedGoing !== row.going) delete next[row.fixture_id];
          }
          for (const id of reconciliation.confirmed) {
            const going = reconciliation.rows.find(row => row.fixture_id === id)?.going;
            next[id] = { error: false, expectedGoing: going, message: current[id]?.error ? "Your saved plan is up to date." : going ? "✓ You're going to this one." : "Back on your Interested list." };
          }
          for (const id of reconciliation.retry) next[id] = { error: false, message: "Your change was saved. Checking the latest plan…" };
          for (const id of reconciliation.changed) next[id] = { error: false, message: "Your saved plan has changed. Showing the latest state." };
          return next;
        });
        if (reconciliation.changed.some(id => !reconciliation.rows.some(row => row.fixture_id === id))) setError("The latest saved list no longer includes this match.");
        setLoading(false);
        if (reconciliation.retry.length && attempt === 0) continue;
        return;
      } catch (requestError) {
        if (generation !== requestGeneration.current) return;
        const message = apiErrorMessage(requestError, "We couldn't refresh your matchdays. Please try again.");
        if (confirmedGoing.current.size) setPlanFeedback(current => {
          const next = { ...current };
          for (const [id, confirmation] of confirmedGoing.current) next[id] = { error: true, expectedGoing: confirmation.going, message: `Your change was saved, but we couldn't refresh it. ${message}` };
          return next;
        });
        else setError(message);
        setLoading(false);
        return;
      }
    }
  }, []);

  useEffect(() => { void loadMatchdays(); }, [loadMatchdays]);
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === "visible" && savingGoing.current.size === 0) void loadMatchdays(); };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => { window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, [loadMatchdays]);
  useEffect(() => {
    const id = focusFixture.current;
    if (id === null || updatingFixtureIds.includes(id)) return;
    focusFixture.current = null;
    if (document.activeElement === document.body || document.activeElement?.id === `going-button-${id}`) document.getElementById(`going-button-${id}`)?.focus();
  }, [updatingFixtureIds]);
  useEffect(() => () => { requestGeneration.current++; }, []);
  useEffect(() => { const clock = window.setInterval(() => setMatchdayNow(new Date()), 60_000); return () => window.clearInterval(clock); }, []);
  const attendedFixtureIds = useMemo(() => new Set(attendedFixtures.map((fixture) => fixture.fixture_id)), [attendedFixtures]);
  const sections = useMemo(() => partitionMatchdays(fixtures, attendedFixtureIds, matchdayNow), [fixtures, attendedFixtureIds, matchdayNow]);
  const upcomingFixtures = sections.going;
  const interestedFixtures = sections.interested;
  const unresolvedFixtures = sections.awaiting;
  const toggleGoing = async (fixture: InterestedFixture) => {
    if (savingGoing.current.has(fixture.fixture_id) || updatingFixtureIds.includes(fixture.fixture_id) || typeof fixture.going !== "boolean") return;
    savingGoing.current.add(fixture.fixture_id);
    focusFixture.current = fixture.fixture_id;
    requestGeneration.current++;
    setUpdatingFixtureIds((current) => [...current, fixture.fixture_id]); setError("");
    setPlanFeedback(current => { const next = { ...current }; delete next[fixture.fixture_id]; return next; });
    try {
      const going = !fixture.going;
      const response = await api.put(`/fixtures/${fixture.fixture_id}/going`, { going });
      if (response.data.going !== going) throw new Error("Intention was not confirmed");
      requestGeneration.current++;
      confirmedGoing.current.set(fixture.fixture_id, { fixture, going, checked: false });
      trackEvent(going ? "going_selected" : "going_removed", { surface: "matchdays" });
      setFixtures((current) => current.map((item) => item.fixture_id === fixture.fixture_id ? { ...item, going } : item));
      setPlanFeedback(current => ({ ...current, [fixture.fixture_id]: { error: false, expectedGoing: going, message: going ? "✓ You're going to this one." : "Back on your Interested list." } }));
      await loadMatchdays();
    }
    catch (requestError) { setPlanFeedback(current => ({ ...current, [fixture.fixture_id]: { error: true, message: apiErrorMessage(requestError, "We couldn't update your plan. Try again.") } })); }
    finally { savingGoing.current.delete(fixture.fixture_id); setUpdatingFixtureIds((current) => current.filter((id) => id !== fixture.fixture_id)); }
  };

  const resolveCompletedFixture = async (fixture: InterestedFixture, attended: boolean) => {
    if (updatingFixtureIds.includes(fixture.fixture_id)) return;
    setAttendanceResolution(null); setUpdatingFixtureIds((current) => [...current, fixture.fixture_id]); setFixtures((current) => current.filter((item) => item.fixture_id !== fixture.fixture_id)); setError("");
    try { if (attended && !attendedFixtureIds.has(fixture.fixture_id)) await api.post(`/fixtures/${fixture.fixture_id}/attendance`); if (!attended) await api.delete(`/fixtures/${fixture.fixture_id}/interested`); if (attended) setAttendanceResolution(fixture); await loadMatchdays(); }
    catch (requestError) { setError(apiErrorMessage(requestError, "We couldn't update this matchday. Try again.")); await loadMatchdays(); }
    finally { setUpdatingFixtureIds((current) => current.filter((id) => id !== fixture.fixture_id)); }
  };

  const empty = !loading && upcomingFixtures.length === 0 && interestedFixtures.length === 0 && unresolvedFixtures.length === 0 && attendedFixtures.length === 0 && photoAttendances.length === 0;
  const linkFooter = (fixtureId: number) => <Link href={`/fixture/${fixtureId}`} className="tt-action inline-flex min-w-0 items-center justify-center whitespace-nowrap px-1 text-center sm:px-2">View match →</Link>;

  const planFooter = (fixture: InterestedFixture) => {
    const pending = updatingFixtureIds.includes(fixture.fixture_id);
    const feedback = planFeedback[fixture.fixture_id];
    return <div><div className="grid grid-cols-2 gap-2">
        {linkFooter(fixture.fixture_id)}
        {typeof fixture.going === "boolean" && <button id={`going-button-${fixture.fixture_id}`} type="button" aria-pressed={fixture.going} aria-busy={pending} aria-describedby={feedback ? `going-feedback-${fixture.fixture_id}` : undefined} disabled={pending} onClick={() => void toggleGoing(fixture)} className={`tt-going-intention min-w-0 cursor-pointer whitespace-nowrap px-2 text-center focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)] disabled:cursor-wait disabled:opacity-60 ${fixture.going
          ? "inline-flex min-h-11 items-center justify-center border-2 border-[color-mix(in_srgb,var(--tt-gold)_70%,var(--tt-ink))] bg-[color-mix(in_srgb,var(--tt-gold)_20%,var(--tt-paper))] text-xs font-extrabold uppercase text-[var(--tt-ink)]"
          : "tt-action tt-action-secondary"}`}>
          {pending ? "Saving..." : fixture.going ? <><span aria-hidden="true" className="mr-1">✓</span> Going</> : "I'm Going"}
        </button>}
    </div>{feedback && <p id={`going-feedback-${fixture.fixture_id}`} role={feedback.error ? "alert" : "status"} className={`mt-2 text-sm font-semibold ${feedback.error ? "text-red-800" : "text-[var(--brand-interactive)]"}`}>{feedback.message}</p>}{feedback?.error && confirmedGoing.current.has(fixture.fixture_id) && <button type="button" onClick={() => void loadMatchdays()} className="min-h-11 text-sm font-bold underline">Refresh saved plan</button>}</div>;
  };

  return <main className="mx-auto max-w-6xl px-4 py-7 sm:px-6 sm:py-10">
    <header className="border-b-[3px] border-[var(--tt-ink)] pb-4"><h1 className="tt-display text-4xl leading-none sm:text-5xl">My Matchdays</h1><p className="mt-2 text-sm text-[var(--tt-muted)]">The occasions you&apos;re looking forward to and the matches you remember.</p><p className="mt-1 text-xs text-[var(--tt-muted)]">Times shown in your current timezone.</p></header>
    {loading && <p className="mt-8 font-semibold text-[var(--tt-muted)]">Loading your matchdays…</p>}{error && <p role="alert" className="mt-6 border-l-4 border-red-700 bg-[var(--tt-paper)] px-4 py-3 font-semibold text-red-800">{error}</p>}{attendanceResolution && <section role="status" className="mt-5 border border-[var(--brand-interactive)] bg-[var(--tt-paper)] p-4">
      <h2 className="tt-display text-2xl leading-none text-[var(--brand-interactive)]">✓ Matchday recorded</h2>
      <p className="mt-2 break-words font-bold">{attendanceResolution.home_team} vs {attendanceResolution.away_team}</p>
      <p className="mt-1 text-sm text-[var(--tt-muted)]">Added to your football history.</p>
      <Link href="/my-stadiums" className="mt-3 inline-flex min-h-11 items-center text-xs font-extrabold uppercase text-[var(--brand-interactive)] underline underline-offset-4">View my football world →</Link>
    </section>}
    {empty && <section className="tt-panel mt-7 border-l-[8px] border-l-[var(--brand-interactive)] p-6"><p className="tt-kicker">Your matchday history starts here</p><p className="mt-2 max-w-xl text-sm leading-6 text-[var(--tt-muted)]">Shortlist a fixture, then come back after the match to remember the occasion.</p><Link href="/" className="tt-action mt-5 inline-flex items-center justify-center px-5">Find a match →</Link></section>}
    {!loading && upcomingFixtures.length > 0 && <section className="tt-section-rule mt-7 pt-3" aria-labelledby="up-next-heading"><h2 id="up-next-heading" className="tt-display text-3xl leading-none sm:text-4xl">Going</h2><p className="mt-1 text-base text-[var(--tt-muted)]">Your upcoming matchdays.</p><div className="mt-4 grid gap-4 md:grid-cols-2">{previewItems(upcomingFixtures, UPCOMING_PREVIEW_LIMIT, showAllUpcoming).map((fixture) => <MatchdayCard key={fixture.fixture_id} fixture={fixture} venueName={fixture.venue_name} venueCity={fixture.venue_city} state="upcoming" footer={planFooter(fixture)} />)}</div><ExpandButton expanded={showAllUpcoming} hiddenCount={upcomingFixtures.length - UPCOMING_PREVIEW_LIMIT} onClick={() => setShowAllUpcoming((value) => !value)} label="View all" /></section>}
    {!loading && interestedFixtures.length > 0 && <section className="tt-section-rule mt-7 pt-3" aria-labelledby="interested-heading"><h2 id="interested-heading" className="tt-display text-3xl leading-none sm:text-4xl">Interested</h2><p className="mt-1 text-base text-[var(--tt-muted)]">Matches you&apos;re thinking about.</p><div className="mt-4 grid gap-4 md:grid-cols-2">{previewItems(interestedFixtures, UPCOMING_PREVIEW_LIMIT, showAllInterested).map((fixture) => <MatchdayCard key={fixture.fixture_id} fixture={fixture} venueName={fixture.venue_name} venueCity={fixture.venue_city} state="upcoming" footer={planFooter(fixture)} />)}</div><ExpandButton expanded={showAllInterested} hiddenCount={interestedFixtures.length - UPCOMING_PREVIEW_LIMIT} onClick={() => setShowAllInterested((value) => !value)} label="View all" /></section>}
    {!loading && unresolvedFixtures.length > 0 && <section className="tt-section-rule mt-9 pt-3" aria-labelledby="answer-heading"><h2 id="answer-heading" className="tt-display text-3xl leading-none sm:text-4xl">Did You Go?</h2><p className="mt-1 text-base text-[var(--tt-muted)]">Did you attend? Available from three hours after kickoff; this does not confirm the match finished.</p><div className="mt-4 grid gap-4">{previewItems(unresolvedFixtures, ANSWER_PREVIEW_LIMIT, showAllAnswers).map((fixture) => { const updating = updatingFixtureIds.includes(fixture.fixture_id); return <MatchdayCard key={fixture.fixture_id} fixture={fixture} venueName={fixture.venue_name} venueCity={fixture.venue_city} state="answer" footer={<div className="flex flex-wrap items-center gap-x-4"><button type="button" disabled={updating} onClick={() => void resolveCompletedFixture(fixture, true)} className="tt-action px-4">{updating ? "Saving…" : "Yes, I was there"}</button><button type="button" disabled={updating} onClick={() => void resolveCompletedFixture(fixture, false)} className="min-h-11 text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-muted)] underline decoration-2 underline-offset-4">Didn&apos;t go</button></div>} />; })}</div><ExpandButton expanded={showAllAnswers} hiddenCount={unresolvedFixtures.length - ANSWER_PREVIEW_LIMIT} onClick={() => setShowAllAnswers((value) => !value)} label="More to answer" /></section>}
    {!loading && (attendedFixtures.length > 0 || photoAttendances.length > 0) && <section className="tt-section-rule mt-9 pt-3" aria-labelledby="past-heading"><div className="flex items-end justify-between gap-3"><div><h2 id="past-heading" className="tt-display text-3xl leading-none sm:text-4xl">Went</h2><p className="mt-1 text-base text-[var(--tt-muted)]">The football you&apos;ve been to.</p></div><span className="text-sm font-extrabold uppercase tracking-[0.1em] text-[var(--tt-muted)]">{attendedFixtures.length} matches</span></div><div className="mt-5 grid gap-4 md:grid-cols-2">{previewItems(attendedFixtures, PAST_PREVIEW_LIMIT, showAllPast).map((fixture) => <MatchdayCard key={fixture.fixture_id} fixture={fixture} venueName={fixture.venue_name} venueCity={fixture.venue_city} state="attended" footer={<>{linkFooter(fixture.fixture_id)}{photoAttendances.filter(visit => visit.fixture_id === fixture.fixture_id).map(visit => <TerracePhotoSubmission key={`${email}:${visit.visit_id}`} attendance={visit} />)}</>} />)}</div><div className="mt-4 grid gap-4 md:grid-cols-2">{photoAttendances.filter(visit => !attendedFixtures.some(fixture => fixture.fixture_id === visit.fixture_id)).map(visit => <article key={visit.visit_id} className="tt-panel min-w-0 p-4"><h3 className="tt-display break-words text-2xl">{visit.venue_name}</h3><p className="mt-2 text-sm">Historical matchday &middot; {visit.match_date ? visit.match_date : "Date not recorded"}</p><TerracePhotoSubmission key={`${email}:${visit.visit_id}`} attendance={visit} /></article>)}</div><ExpandButton expanded={showAllPast} hiddenCount={attendedFixtures.length - PAST_PREVIEW_LIMIT} onClick={() => setShowAllPast((value) => !value)} label="View all matchdays" /></section>}
  </main>;
}
