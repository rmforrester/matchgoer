"use client";

import axios from "axios";
import { useAuth } from "./AuthProvider";
import { accountRoute, signinRoute } from "../../lib/auth-flow";
import { eligibleAttendanceFixture, isFutureAttendanceDate, localAttendanceToday } from "../../lib/attendance-eligibility";
import { apiErrorMessage, emptyGuestHistory, historyLoadError } from "../../lib/api-error";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import api from "../../lib/api";
import type { FootprintSummary, GroundReview, MyGround, MyGroundFootprint } from "../types/grounds";
import MatchdayTips from "./MatchdayTips";
import GroundPhotograph from "./GroundPhotograph";
import { footballCountry, footballPassport } from "../../lib/my-grounds";

import FootprintLeagues from "./FootprintLeagues";
import { footprintGrounds, type FootprintPeriod } from "../../lib/football-footprint";

const PersonalGroundMap = dynamic(() => import("./PersonalGroundMap"), { ssr: false });

type VenueResult = { venue_id: number; name: string; city: string | null };
type FixtureCandidate = { status: string | null; fixture_id: number; fixture_date: string; home_team: string; away_team: string; league_name: string };

const reviewLabel = (review: GroundReview | null) =>
  !review || review.state === "blank" ? "Rate this ground" : review.state === "partial" ? "Continue review" : "Edit my review";

const knownDate = (value: string | null) => {
  if (!value) return "Unknown";
  const date = new Date(`${value}T00:00:00`);
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
};

export default function VisitedTab() {
  const { accountKey } = useAuth();
  return <VisitedTabContent key={accountKey} />;
}

function VisitedTabContent() {
  const { authenticated, loading: authLoading, issue: authIssue } = useAuth();
  const requestedReview = useSearchParams().get("review");
  const requestedVenue = useSearchParams().get("recordVenue");
  const [selectedFixtureId, setSelectedFixtureId] = useState<number | null>(null);
  const [grounds, setGrounds] = useState<MyGround[]>([]);
  const [footprint, setFootprint] = useState<FootprintSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const historySeen = useRef(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<VenueResult[]>([]);
  const [selected, setSelected] = useState<VenueResult | null>(null);
  const recordHeading = useRef<HTMLHeadingElement>(null);
  const [visitDate, setVisitDate] = useState("");
  const [saving, setSaving] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [pastMatchDate, setPastMatchDate] = useState("");
  const [fixtureCandidates, setFixtureCandidates] = useState<FixtureCandidate[]>([]);
  const [findingMatches, setFindingMatches] = useState(false);
  const [searchedMatchDate, setSearchedMatchDate] = useState("");
  const matchSearch = useRef(0);
  useEffect(() => () => { matchSearch.current += 1; }, []);
  const [editingVisitId, setEditingVisitId] = useState<number | null>(null);
  const [timeframe, setTimeframe] = useState<FootprintPeriod>("lifetime");
  const [reviewingId, setReviewingId] = useState<number | null>(null);
  const [ratingMessage, setRatingMessage] = useState("");
  const savingReview = useRef(false);
  const [savedVenueId, setSavedVenueId] = useState<number | null>(null);
  const returnFocusVenue = useRef<number | null>(null);
  useEffect(() => {
    if (reviewingId !== null || returnFocusVenue.current === null) return;
    const summary = document.getElementById(`personal-review-${returnFocusVenue.current}`);
    summary?.focus({ preventScroll: true });
    summary?.scrollIntoView({ block: "start", behavior: "instant" });
    returnFocusVenue.current = null;
  }, [reviewingId, ratingMessage]);
  const reviewHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (reviewingId === null || loading) return;
    const frame = window.requestAnimationFrame(() => {
      reviewHeading.current?.focus({ preventScroll: true });
      reviewHeading.current?.scrollIntoView({ block: "start", behavior: "instant" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [reviewingId, loading]);
  const [showAddGround, setShowAddGround] = useState(false);
  useEffect(() => {
    if (!selected || loading) return;
    const frame = window.requestAnimationFrame(() => {
      recordHeading.current?.focus({ preventScroll: true });
      recordHeading.current?.closest("section")?.scrollIntoView({ block: "start", behavior: "instant" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [selected, showAddGround, loading]);
  const [collection, setCollection] = useState<{ country: string } | "all" | null>(null);
  const [scores, setScores] = useState({ atmosphere: null as number | null, pubs: null as number | null, travel: null as number | null, facilities: null as number | null, recommend: null as boolean | null });

  const loadGrounds = useCallback(async () => {
    const session = await api.get("/session");
    if (emptyGuestHistory(session.data, authenticated, authIssue) && !historySeen.current) {
      setError(""); return [];
    }
    const response = await api.get<MyGroundFootprint | MyGround[]>("/my-grounds", { params: { footprint: true } });
    // Old-backend compatibility: keep Lifetime usable without inventing seasons.
    const loaded = Array.isArray(response.data) ? response.data : response.data.grounds;
    setFootprint(Array.isArray(response.data) ? null : response.data.footprint);
    setGrounds(loaded);
    if (loaded.length) historySeen.current = true;
    setError("");
    return loaded;
  }, [authenticated, authIssue]);

  const showReview = (ground: MyGround) => {
    setRatingMessage(""); setError("");
    setReviewingId(ground.venue_id);
    setScores({
      atmosphere: ground.review?.atmosphere_score ?? null,
      pubs: ground.review?.pubs_score ?? null,
      travel: ground.review?.getting_there_score ?? null,
      facilities: ground.review?.facilities_score ?? null,
      recommend: ground.review?.recommend ?? null,
    });
  };

  const openReview = useCallback(async (ground: MyGround) => {
    setSaving(true); setError("");
    try {
      let current = ground;
      if (!ground.review) {
        try { await api.post(`/venues/${ground.venue_id}/away-day-reviews`, { venue_id: ground.venue_id }); }
        catch (requestError) { if (!axios.isAxiosError(requestError) || requestError.response?.status !== 409) throw requestError; }
        current = (await loadGrounds()).find((item) => item.venue_id === ground.venue_id) ?? ground;
      }
      showReview(current);
    } catch (requestError) {
      setError(apiErrorMessage(requestError, "Unable to open your review."));
    } finally { setSaving(false); }
  }, [loadGrounds]);

  useEffect(() => {
    if (authLoading) return;
    // The state update happens after the session/API promises resolve.
    loadGrounds().then((loaded) => {
      const ground = loaded.find((item) => item.venue_id === Number(requestedReview));
      if (requestedReview && ground) {
        setCollection("all");
        if (!ground.review || ground.review.state === "blank") void openReview(ground);
        else window.requestAnimationFrame(() => {
          const summary = document.getElementById(`personal-review-${ground.venue_id}`);
          summary?.focus({ preventScroll: true });
          summary?.scrollIntoView({ block: "start", behavior: "instant" });
        });
      }
    }).catch((requestError) => setError(historyLoadError(requestError, "Unable to load My Grounds. Please try again."))).finally(() => setLoading(false));
  }, [loadGrounds, openReview, requestedReview, authLoading, loadAttempt]);

  useEffect(() => {
    if (!requestedVenue) return;
    const venueId = Number(requestedVenue);
    if (!Number.isSafeInteger(venueId) || venueId <= 0) return;
    let cancelled = false;
    void api.get("/session").then(() => api.get(`/venue/${venueId}`)).then(response => {
      if (cancelled) return;
      if (Number(response.data.venue_id) !== venueId) throw new Error("Venue identity mismatch");
      setSelected(response.data); setShowAddGround(true);
      setVisitDate(""); setSelectedFixtureId(null);
    }).catch(() => { if (!cancelled) setError("Unable to open this ground's matchday entry. Try again."); });
    return () => { cancelled = true; };
  }, [requestedVenue]);

  const search = async () => {
    if (query.trim().length < 2) return;
    setSearching(true); setError("");
    try { setResults((await api.get("/venues/search", { params: { q: query.trim(), limit: 20 } })).data); }
    catch { setError("Unable to search for grounds."); }
    finally { setSearching(false); }
  };

  const addVisit = async (venueId: number, date: string, done: () => void) => {
    if (saving || isFutureAttendanceDate(date)) return;
    setSaving(true); setError("");
    try {
      const saved = await api.post<{ visit_id: number }>(`/venues/${venueId}/visits`, { visit_date: date || null, calendar_utc_offset_minutes: -new Date().getTimezoneOffset() });
      historySeen.current = true;
      const loaded = await loadGrounds();
      if (!Number.isInteger(saved.data.visit_id) || !loaded.some(ground => ground.venue_id === venueId && ground.visits.some(visit => visit.visit_id === saved.data.visit_id))) throw new Error("Visit persistence not confirmed");
      done();
    }
    catch (requestError) { setError(historyLoadError(requestError, "Your matchday could not be confirmed. Check your history before trying again.")); }
    finally { setSaving(false); }
  };

  const submitReview = async () => {
    if (reviewingId === null || saving || savingReview.current) return;
    const venueId = reviewingId;
    savingReview.current = true; setSaving(true); setError(""); setRatingMessage("");
    try {
      const { data } = await api.patch<GroundReview & { venue_id: number }>(`/venues/${venueId}/away-day-reviews`, { recommend: scores.recommend, atmosphere_score: scores.atmosphere, pubs_score: scores.pubs, getting_there_score: scores.travel, facilities_score: scores.facilities });
      if (data.venue_id !== venueId || !Number.isInteger(data.review_id)) throw new Error("Rating not confirmed");
      const complete = [data.overall_score, data.atmosphere_score, data.pubs_score, data.getting_there_score, data.facilities_score].every(value => value !== null) && data.recommend !== null;
      setGrounds(current => current.map(ground => ground.venue_id === venueId ? { ...ground, review: { ...data, state: complete ? "completed" : "partial", completed: complete } } : ground));
      returnFocusVenue.current = venueId; setSavedVenueId(venueId); setReviewingId(null); setRatingMessage("RATING SAVED");
      // Reuse the persisted response; an unrelated refresh cannot turn
      // this acknowledged write into a failure or overwrite it with old data.
    } catch { setError("Couldn't save your rating. Try again."); }
    finally { savingReview.current = false; setSaving(false); }
  };

  const findPastMatches = async (venueId: number, date = pastMatchDate) => {
    if (!date || findingMatches || isFutureAttendanceDate(date)) return;
    const request = ++matchSearch.current;
    setFindingMatches(true); setError(""); setFixtureCandidates([]); setSearchedMatchDate("");
    try {
      const response = await api.get(`/venues/${venueId}/fixtures`, { params: { around_date: date, days: 7 } });
      if (request !== matchSearch.current) return;
      setFixtureCandidates(response.data.filter((fixture: FixtureCandidate) => eligibleAttendanceFixture(fixture, venueId)));
      setSearchedMatchDate(date);
    } catch (requestError) {
      if (request === matchSearch.current) setError(apiErrorMessage(requestError, "Unable to find likely matches."));
    } finally { if (request === matchSearch.current) setFindingMatches(false); }
  };

  const updateVisitFixture = async (ground: MyGround, visitId: number, fixtureId: number | null) => {
    if (saving) return;
    setSaving(true); setError("");
    try {
      await api.patch(`/venues/${ground.venue_id}/visits/${visitId}`, { fixture_id: fixtureId });
      await loadGrounds(); setEditingVisitId(null); setFixtureCandidates([]); setPastMatchDate("");
    } catch (requestError) { setError(apiErrorMessage(requestError, "Unable to update this visit.")); }
    finally { setSaving(false); }
  };

  const recordSelectedFixture = async (fixtureId: number) => {
    if (!selected || saving || isFutureAttendanceDate(visitDate)) return;
    setSaving(true); setError("");
    try {
      const saved = await api.post<{ visit_id: number }>(`/venues/${selected.venue_id}/visits`, { visit_date: visitDate || null, fixture_id: fixtureId });
      historySeen.current = true;
      const loaded = await loadGrounds();
      if (!Number.isInteger(saved.data.visit_id) || !loaded.some(ground => ground.venue_id === selected.venue_id && ground.visits.some(visit => visit.visit_id === saved.data.visit_id && visit.fixture_id === fixtureId))) throw new Error("Visit persistence not confirmed");
      setSelected(null); setVisitDate(""); setQuery(""); setResults([]); setFixtureCandidates([]);
    } catch (requestError) { setError(historyLoadError(requestError, "Your matchday could not be confirmed. Check your history before trying again.")); }
    finally { setSaving(false); }
  };

  const enteredScores = [scores.atmosphere, scores.pubs, scores.travel, scores.facilities].filter((score): score is number => score !== null);
  const overall = enteredScores.length ? (enteredScores.reduce((sum, score) => sum + score, 0) / enteredScores.length).toFixed(1) : "—";
  const visibleGrounds = useMemo(() => footprintGrounds(grounds, timeframe, footprint), [grounds, timeframe, footprint]);
  const cityCount = new Set(visibleGrounds.flatMap((ground) => ground.venue_city ? [ground.venue_city.trim().toLocaleLowerCase()] : [])).size;
  const passport = useMemo(() => footballPassport(visibleGrounds), [visibleGrounds]);
  const countryCount = passport.length;
  const matchdayCount = visibleGrounds.reduce((total, ground) => total + ground.visit_count, 0);
  const unplottableCount = visibleGrounds.filter((ground) => ground.latitude === null || ground.longitude === null).length;

  const renderReviewPanel = (ground: MyGround) => <section id={`review-form-${ground.venue_id}`} className="mt-4 border-t border-[var(--tt-rule)] pt-4" aria-labelledby={`review-heading-${ground.venue_id}`}>

    <h3 ref={reviewHeading} tabIndex={-1} id={`review-heading-${ground.venue_id}`} className="sr-only scroll-mt-4">{reviewLabel(ground.review)}</h3>

    <div className="mt-3"><p className="sr-only">Overall preview: {overall} / 10</p><div className="grid gap-4 sm:grid-cols-2">{([['Atmosphere','atmosphere'],['Pubs & food','pubs'],['Getting there','travel'],['Stadium experience','facilities']] as const).map(([label,key]) => <fieldset key={key}><legend className="tt-kicker">{label}</legend><div className="mt-2 flex flex-wrap gap-1">{[1,2,3,4,5,6,7,8,9,10].map((score) => <button key={score} type="button" aria-pressed={scores[key] === score} onClick={() => setScores((current) => ({ ...current, [key]: score }))} className={`min-h-10 min-w-10 border-2 border-[var(--tt-ink)] text-sm font-bold ${scores[key] === score ? "bg-[var(--brand-interactive)] text-[var(--tt-paper)]" : "bg-[var(--tt-paper)]"}`}>{score}</button>)}</div></fieldset>)}</div><fieldset className="mt-6"><legend className="tt-kicker">Would you recommend this ground?</legend><div className="mt-2 flex gap-2"><button type="button" aria-pressed={scores.recommend === true} onClick={() => setScores((current) => ({...current,recommend:true}))} className={`tt-action px-5 ${scores.recommend === true ? "" : "tt-action-secondary"}`}>Yes</button><button type="button" aria-pressed={scores.recommend === false} onClick={() => setScores((current) => ({...current,recommend:false}))} className={`tt-action px-5 ${scores.recommend === false ? "" : "tt-action-secondary"}`}>No</button></div></fieldset>
      <MatchdayTips venueId={ground.venue_id} inline />
      {error && <p role="alert" className="mt-4 text-sm font-bold text-red-800">{error}</p>}
      <div className="mt-4 grid grid-cols-2 gap-2"><button type="button" disabled={saving} onClick={() => { showReview(ground); returnFocusVenue.current = ground.venue_id; setReviewingId(null); setError(""); }} className="tt-action tt-action-secondary px-5">Cancel</button><button type="button" disabled={saving || (scores.recommend === null && enteredScores.length === 0)} onClick={() => void submitReview()} className="tt-action px-5">{saving ? "Saving…" : "Save review"}</button></div>
    </div>
  </section>;

  const renderPersonalReview = (ground: MyGround, contained = false) => {
    const review = ground.review;
    const hasRating = review && (review.overall_score !== null || review.recommend !== null);
    const editing = reviewingId === ground.venue_id;
    if (!hasRating && !editing) return null;
    return <section id={`personal-review-${ground.venue_id}`} tabIndex={-1} aria-label={`Your verdict for ${ground.venue_name}`} className={`${contained ? "mt-2" : "tt-panel mt-4 p-3 sm:p-4"} scroll-mt-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]`}>
      <div className="flex items-start gap-3">
        <GroundPhotograph venueId={ground.venue_id} compact />
        <div className="min-w-0 flex-1">
          {!contained && <h2 className="tt-display break-words text-2xl leading-none">{ground.venue_name}</h2>}
          <h3 className="sr-only">Your verdict</h3>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-bold">
            {review?.overall_score != null && <p><span aria-hidden="true">★ </span><span className="text-lg text-[var(--brand-interactive)]">{review.overall_score.toFixed(1)}</span> / 10</p>}
            {review?.recommend != null && <p className="border-l border-[var(--tt-rule)] pl-3">{review.recommend ? "Would recommend" : "Would not recommend"}</p>}
          </div>
          {savedVenueId === ground.venue_id && ratingMessage && <p role="status" className="mt-2 text-sm font-bold text-[var(--brand-interactive)]">{ratingMessage}</p>}
          <button type="button" disabled={saving} aria-expanded={editing} aria-controls={`review-form-${ground.venue_id}`} onClick={() => {
            if (editing) { showReview(ground); returnFocusVenue.current = ground.venue_id; setReviewingId(null); setError(""); }
            else void openReview(ground);
          }} className="min-h-11 text-xs font-extrabold underline focus-visible:outline-2 focus-visible:outline-offset-2">{editing ? "HIDE REVIEW ↑" : "EDIT MY REVIEW →"}</button>
        </div>
      </div>
      {editing && renderReviewPanel(ground)}
    </section>;
  };

  const renderGround = (ground: MyGround, nested: boolean) => <article key={ground.venue_id} className={`${nested ? "flex min-w-0 flex-col py-4" : "tt-panel flex min-w-0 flex-col p-4"} ${reviewingId === ground.venue_id ? "sm:col-span-2" : ""}`}>
      <h2 className="tt-display break-words text-[1.7rem] leading-[0.94]">{ground.venue_name}</h2><p className="mt-1 text-xs font-bold uppercase tracking-[0.08em] text-[var(--tt-muted)]">{[ground.venue_city, ground.venue_country].filter(Boolean).join(" · ")}</p>
      <p className="mt-3 text-xs font-extrabold uppercase tracking-[0.04em] text-[var(--brand-interactive)]">{ground.visit_count} {ground.visit_count === 1 ? "matchday" : "matchdays"}</p>
      <p className="mt-1 text-sm text-[var(--tt-muted)]">{ground.latest_visit_date ? `Last visited · ${knownDate(ground.latest_visit_date)}` : "Date not recorded"}</p>
      {Number(requestedReview) !== ground.venue_id && renderPersonalReview(ground, true)}
      <div className="mt-4 grid grid-cols-2 gap-2">
        <Link href={`/venue/${ground.venue_id}`} className="tt-action inline-flex min-w-0 items-center justify-center whitespace-nowrap px-1 text-center text-[0.68rem]! tracking-[0.04em]! sm:text-xs! focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">View ground →</Link>
        <button type="button" aria-expanded={expandedId === ground.venue_id} aria-controls={`ground-visits-${ground.venue_id}`} onClick={() => setExpandedId(expandedId === ground.venue_id ? null : ground.venue_id)} className="tt-action tt-action-secondary min-w-0 whitespace-nowrap px-1 text-center text-[0.68rem]! tracking-[0.04em]! sm:text-xs! focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">{expandedId === ground.venue_id ? "Hide visits" : "Visit details"}</button>
      </div>
      {expandedId === ground.venue_id && <ul id={`ground-visits-${ground.venue_id}`} className="mt-4 border-t border-[var(--tt-rule)] pt-3">{ground.visits.map((visit) => { const fixture = ground.attended_fixtures.find((item) => item.fixture_id === visit.fixture_id); return <li key={visit.visit_id} className="border-b border-[var(--tt-rule)] py-3 last:border-0"><p className="text-xs font-bold uppercase tracking-[0.08em] text-[var(--tt-muted)]">{visit.visit_date ? knownDate(visit.visit_date) : "Date not recorded"}</p>{fixture && <><p className="mt-1 font-bold">{fixture.home_team} v {fixture.away_team}</p><p className="mt-1 text-sm text-[var(--tt-muted)]">{fixture.league_name}</p></>}{fixture && <Link href={`/fixture/${fixture.fixture_id}`} className="mt-1 inline-flex min-h-10 items-center text-xs font-extrabold uppercase text-[var(--brand-interactive)] underline">View match →</Link>}<button type="button" onClick={() => { setEditingVisitId(visit.visit_id); setPastMatchDate(visit.visit_date ?? ""); setFixtureCandidates([]); }} className="ml-4 min-h-10 text-xs font-extrabold uppercase text-[var(--brand-interactive)] underline">{fixture ? "Change match" : "Find match"}</button>{fixture && <button type="button" disabled={saving} onClick={() => void updateVisitFixture(ground, visit.visit_id, null)} className="ml-4 min-h-10 text-xs font-extrabold uppercase text-[var(--tt-muted)] underline">Remove link</button>}{editingVisitId === visit.visit_id && <div className="mt-2"><div className="flex flex-wrap gap-2"><input type="date" max={localAttendanceToday()} aria-label="Visit date" value={pastMatchDate} onChange={(event) => { matchSearch.current += 1; setFindingMatches(false); setSearchedMatchDate(""); setPastMatchDate(event.target.value); setFixtureCandidates([]); }} className="tt-control px-3"/><button type="button" disabled={!pastMatchDate || findingMatches || isFutureAttendanceDate(pastMatchDate)} onClick={() => void findPastMatches(ground.venue_id)} className="tt-action px-3">Find match (optional)</button></div>{fixtureCandidates.map((candidate) => <button key={candidate.fixture_id} type="button" disabled={saving} onClick={() => void updateVisitFixture(ground, visit.visit_id, candidate.fixture_id)} className="mt-2 block min-h-10 text-left font-bold text-[var(--brand-interactive)] underline">{candidate.home_team} v {candidate.away_team} · {knownDate(candidate.fixture_date.slice(0, 10))}</button>)}</div>}</li>; })}</ul>}
    </article>;

  const recordForm = selected && <section id="record-matchday" aria-labelledby="record-matchday-heading" className="tt-panel mt-4 p-5">
    <h3 ref={recordHeading} tabIndex={-1} id="record-matchday-heading" className="tt-display text-3xl focus-visible:outline-2 focus-visible:outline-offset-2">Record matchday</h3>
    <p className="mt-2 font-bold break-words">{selected.name}</p>{selected.city && <p className="break-words text-[var(--tt-muted)]">{selected.city}</p>}
    <p className="mt-3 text-sm">Enter the date, then find the match if you remember it. Leave the date blank for an undated visit.</p>
    <label htmlFor="new-visit-date" className="tt-kicker mt-4 block">Match date (optional)</label>
    <input id="new-visit-date" type="date" max={localAttendanceToday()} value={visitDate} onChange={event => { matchSearch.current += 1; setFindingMatches(false); setSearchedMatchDate(""); setVisitDate(event.target.value); setFixtureCandidates([]); setSelectedFixtureId(null); }} className="tt-control mt-2 max-w-full px-3" />
    {visitDate && <button type="button" disabled={findingMatches || saving || isFutureAttendanceDate(visitDate)} onClick={() => void findPastMatches(selected.venue_id, visitDate)} className="mt-2 block min-h-11 text-left text-xs font-extrabold uppercase text-[var(--brand-interactive)] underline">{findingMatches ? "Finding matches…" : "Find match (optional)"}</button>}
    {visitDate && searchedMatchDate === visitDate && !findingMatches && !isFutureAttendanceDate(visitDate) && fixtureCandidates.length === 0 && <div role="status" className="mt-3"><h4 className="font-extrabold">CAN&apos;T FIND YOUR MATCH?</h4><p className="mt-1 text-sm">You can still record your visit using the ground and date.</p></div>}
    {fixtureCandidates.map(fixture => <button key={fixture.fixture_id} type="button" aria-pressed={selectedFixtureId === fixture.fixture_id} disabled={saving} onClick={() => { setSelectedFixtureId(fixture.fixture_id); }} className="mt-2 block min-h-11 w-full border-t border-[var(--tt-rule)] py-2 text-left font-bold text-[var(--brand-interactive)]">{selectedFixtureId === fixture.fixture_id ? "✓ " : ""}{fixture.home_team} v {fixture.away_team} · {knownDate(fixture.fixture_date.slice(0, 10))}</button>)}
    {isFutureAttendanceDate(visitDate) && <div role="status" className="mt-3 border-l-4 border-[var(--brand-interactive)] pl-3"><h4 className="font-extrabold">THAT MATCH HASN&apos;T HAPPENED YET</h4><p className="mt-1 text-sm">You can record your matchday once the game has been played.</p></div>}
    <div className="mt-4 flex flex-wrap gap-3">
      <button type="button" disabled={saving} onClick={() => { setSelected(null); setSelectedFixtureId(null); setFixtureCandidates([]); setVisitDate(""); window.requestAnimationFrame(() => document.getElementById("ground-search")?.focus()); }} className="tt-action tt-action-secondary px-4">Change ground</button>
      <button type="button" disabled={saving || isFutureAttendanceDate(visitDate)} onClick={() => {
        if (selectedFixtureId !== null) void recordSelectedFixture(selectedFixtureId);
        else void addVisit(selected.venue_id, visitDate, () => { setSelected(null); setVisitDate(""); setQuery(""); setResults([]); setFixtureCandidates([]); });
      }} className="tt-action px-4">{saving ? "Saving…" : "Save matchday"}</button>
    </div>
  </section>;

  return <main className="mx-auto w-full max-w-5xl px-4 py-4 sm:px-6 sm:py-8">
    <header className="border-b-2 border-[var(--tt-ink)] pb-3"><h1 className="tt-display text-4xl leading-none sm:text-5xl">My grounds</h1><p className="mt-2 text-sm text-[var(--tt-muted)]">Football takes you places.</p></header>
    {!loading && requestedReview && grounds.filter(ground => ground.venue_id === Number(requestedReview)).map(ground => <div key={ground.venue_id}>{renderPersonalReview(ground)}</div>)}
    {!loading && (selected !== null || grounds.length === 0 || showAddGround) && recordForm}
    {!loading && grounds.length > 0 && <button type="button" onClick={() => setShowAddGround((current) => !current)} aria-expanded={showAddGround} aria-controls="add-ground" className="tt-action tt-action-secondary mt-4 inline-flex h-11 items-center justify-center whitespace-nowrap px-4 text-xs">{showAddGround ? "Close add ground" : "+ Add a ground"}</button>}
    {!loading && !selected && grounds.length > 0 && showAddGround && <section id="add-ground" className="mt-8 border-t-2 border-[var(--tt-ink)] pt-3" aria-labelledby="add-ground-heading"><h2 id="add-ground-heading" className="tt-display text-3xl leading-none sm:text-4xl">Add a ground</h2>{grounds.length > 0 && <p className="mt-1 text-sm text-[var(--tt-muted)]">Add somewhere you&apos;ve been.</p>}<div className="mt-4 flex flex-wrap gap-2"><label htmlFor="ground-search" className="sr-only">Search for a ground or city</label><input id="ground-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void search(); }} placeholder="Search ground or city" className="tt-control min-w-0 flex-1 px-4"/><button type="button" disabled={searching || query.trim().length < 2} onClick={() => void search()} className="tt-action px-5">{searching ? "Searching…" : "Search"}</button></div>
      {!selected && results.length > 0 && <div className="tt-panel mt-4 divide-y divide-[var(--tt-rule)]">{results.map((venue) => <button key={venue.venue_id} type="button" onClick={() => { setSelected(venue); setSelectedFixtureId(null); setFixtureCandidates([]); }} className="block min-h-12 w-full px-4 py-3 text-left hover:bg-[var(--tt-paper)]"><strong>{venue.name}</strong>{venue.city && <span className="ml-2 text-[var(--tt-muted)]">{venue.city}</span>}{grounds.some((ground) => ground.venue_id === venue.venue_id) && <span className="ml-2 text-xs font-bold uppercase text-[var(--brand-interactive)]">Already visited</span>}</button>)}</div>}
    </section>}
    {error && reviewingId === null && <p role="alert" className="mt-5 border-l-4 border-red-700 bg-[var(--tt-paper)] px-4 py-3 font-semibold text-red-800">{error} <button type="button" onClick={() => { setLoading(true); setError(""); setLoadAttempt(value => value + 1); }} className="min-h-11 underline">Try again</button></p>}
    {loading && <p className="mt-6 font-semibold">Loading your ground history…</p>}
    {!loading && !selected && grounds.length === 0 && <section className="mt-8 border-y-2 border-[var(--tt-ink)] py-8"><p className="tt-display text-3xl">Your football story starts here.</p><p className="mt-2 text-[var(--tt-muted)]">Add somewhere you&apos;ve been.</p>{authenticated && <a href="#add-ground" className="tt-action mt-4 inline-flex min-h-11 items-center justify-center px-4">Add a ground →</a>}</section>}

    {!loading && grounds.length > 0 && <section className="mt-5" aria-label="Visited grounds map"><div className="mb-4 inline-flex max-w-full overflow-x-auto border-b border-[var(--tt-rule)]" aria-label="Show visits from">{([{ key: "lifetime", label: "Lifetime" }, { key: "season", label: "This Season" }] as const).map((option) => <button key={option.key} type="button" aria-pressed={timeframe === option.key} disabled={option.key === "season" && !footprint} onClick={() => { setTimeframe(option.key); setCollection(null); }} className={`min-h-11 shrink-0 border-b-2 px-3 text-[0.68rem] font-extrabold uppercase tracking-[0.06em] ${timeframe === option.key ? "border-[var(--brand-interactive)] text-[var(--brand-interactive)]" : "border-transparent text-[var(--tt-muted)]"}`}>{option.label}</button>)}</div>{!footprint && <p className="mb-3 text-xs text-[var(--tt-muted)]">Season coverage isn&apos;t available right now. Your Lifetime history is here.</p>}{timeframe === "season" && <p className="mb-3 text-xs text-[var(--tt-muted)]">Dated visits within verified current league seasons. Undated and unclassified visits stay in Lifetime.</p>}{visibleGrounds.length > 0 ? <PersonalGroundMap grounds={visibleGrounds}/> : <div className="border-y-2 border-[var(--tt-ink)] py-6"><p className="font-bold">No recorded visits in a verified current season.</p><p className="mt-1 text-sm text-[var(--tt-muted)]">Your full ground history is in Lifetime.</p></div>}{unplottableCount > 0 && <p className="mt-2 text-xs font-bold text-[var(--tt-muted)]">{unplottableCount} visited {unplottableCount === 1 ? "ground could" : "grounds could"} not be plotted because coordinates are unavailable.</p>}</section>}

    {!loading && grounds.length > 0 && <section className="mt-5 border-y border-[var(--tt-rule)] py-4" aria-labelledby="footprint-heading">
      <h2 id="footprint-heading" className="tt-display text-2xl leading-none text-[var(--brand-interactive)] sm:text-3xl">By the numbers</h2>
      <p className="mt-2 text-xs text-[var(--tt-muted)]">Every ground has a story.</p>
      <dl className="mt-4 grid grid-cols-3 divide-x divide-[var(--tt-rule)]">
        {[[visibleGrounds.length, "Grounds"], [countryCount, "Countries"], [matchdayCount, "Matchdays"]].map(([value, label]) => <div key={label} className="flex min-w-0 flex-col px-1 first:pl-0 sm:px-3">
          <dt className="mt-1 text-[0.65rem] font-extrabold uppercase tracking-[0.04em] sm:text-xs">{label}</dt>
          <dd className="tt-display order-first text-4xl leading-none text-[var(--brand-interactive)] sm:text-5xl">{value}</dd>
        </div>)}
      </dl>
      <p className="mt-4 text-xs font-extrabold uppercase tracking-[0.04em] text-[var(--tt-muted)]">{cityCount} cities explored</p>
    </section>}

    {!loading && passport.length > 0 && <section className="mt-6" aria-labelledby="passport-heading">
      <h2 id="passport-heading" className="tt-display text-2xl leading-none text-[var(--brand-interactive)] sm:text-3xl">Your football passport</h2>
      <p className="mt-2 text-xs text-[var(--tt-muted)]">The countries football has taken you to.</p>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {passport.map((country) => {
          const isOpen = collection !== null && collection !== "all" && collection.country === country.key;
          const panelId = `passport-grounds-${encodeURIComponent(country.key)}`;
          return <li key={country.key} className={`min-w-0 border border-[var(--tt-rule)] ${isOpen ? "sm:col-span-2 lg:col-span-3" : ""}`}>
            <h3><button type="button" aria-expanded={isOpen} aria-controls={panelId} onClick={() => setCollection(isOpen ? null : { country: country.key })} className="block min-h-11 w-full px-3 py-3 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">
              <span className="flex items-start justify-between gap-3"><span className="tt-display min-w-0 break-words text-2xl leading-none text-[var(--brand-interactive)]">{country.name}</span><span aria-hidden="true" className="shrink-0 text-[var(--brand-interactive)]">{isOpen ? "⌃" : "⌄"}</span></span>
              <span className="mt-2 block text-xs font-extrabold uppercase tracking-[0.04em]">{country.groundCount} {country.groundCount === 1 ? "ground" : "grounds"} · {country.matchdayCount} {country.matchdayCount === 1 ? "matchday" : "matchdays"}</span>
            </button></h3>
            {isOpen && <div id={panelId} className="mx-3 border-t border-[var(--tt-rule)] divide-y divide-[var(--tt-rule)]">{<FootprintLeagues key={`${country.key}-${timeframe}`} grounds={visibleGrounds.filter((ground) => footballCountry(ground.venue_country)?.key === country.key)} footprint={footprint} period={timeframe} />}</div>}
          </li>;
        })}
      </ul>
    </section>}

    {!loading && visibleGrounds.length > 0 && <div className="mt-5">
      <button type="button" aria-expanded={collection === "all"} aria-controls="all-ground-collection" onClick={() => setCollection(collection === "all" ? null : "all")} className="tt-action tt-action-secondary min-h-11 px-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">{collection === "all" ? "Hide all grounds ↑" : "Show all grounds ↓"}</button>
      {collection === "all" && <section id="all-ground-collection" className="mt-5 border-t-2 border-[var(--tt-ink)] pt-3" aria-labelledby="grounds-list-heading"><h2 id="grounds-list-heading" className="tt-display text-3xl leading-none sm:text-4xl">The grounds you know</h2><div className="mt-4 grid gap-3 sm:grid-cols-2">{visibleGrounds.map((ground) => renderGround(ground, false))}</div></section>}
    </div>}

    {!loading && !selected && grounds.length === 0 && <section id="add-ground" className="mt-8 border-t-2 border-[var(--tt-ink)] pt-3" aria-labelledby="add-ground-heading"><h2 id="add-ground-heading" className="tt-display text-3xl leading-none sm:text-4xl">Add a ground</h2>{grounds.length > 0 && <p className="mt-1 text-sm text-[var(--tt-muted)]">Add somewhere you&apos;ve been.</p>}<div className="mt-4 flex flex-wrap gap-2"><label htmlFor="ground-search" className="sr-only">Search for a ground or city</label><input id="ground-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void search(); }} placeholder="Search ground or city" className="tt-control min-w-0 flex-1 px-4"/><button type="button" disabled={searching || query.trim().length < 2} onClick={() => void search()} className="tt-action px-5">{searching ? "Searching…" : "Search"}</button></div>
      {!selected && results.length > 0 && <div className="tt-panel mt-4 divide-y divide-[var(--tt-rule)]">{results.map((venue) => <button key={venue.venue_id} type="button" onClick={() => { setSelected(venue); setSelectedFixtureId(null); setFixtureCandidates([]); }} className="block min-h-12 w-full px-4 py-3 text-left hover:bg-[var(--tt-paper)]"><strong>{venue.name}</strong>{venue.city && <span className="ml-2 text-[var(--tt-muted)]">{venue.city}</span>}{grounds.some((ground) => ground.venue_id === venue.venue_id) && <span className="ml-2 text-xs font-bold uppercase text-[var(--brand-interactive)]">Already visited</span>}</button>)}</div>}
    </section>}
    {!authLoading && !authenticated && !authIssue && <aside aria-labelledby="guest-history-heading" className="mt-6 border-t border-[var(--tt-rule)] pt-4">
      <h2 id="guest-history-heading" className="tt-display text-2xl">KEEP YOUR FOOTBALL HISTORY</h2>
      <p className="mt-2 text-sm">Sign in or create an account to keep your grounds and matchdays saved.</p>
      <p className="mt-2 text-xs text-[var(--tt-muted)]">Your guest history is linked to this browser until you transfer it to your account. Clearing browser data or closing a private session can lose access.</p>
      <div className="mt-3 flex flex-wrap gap-3"><Link href={accountRoute("/signup", "/my-football?tab=visited")} className="tt-action inline-flex min-h-11 items-center px-4 text-xs">CREATE ACCOUNT</Link><Link href={signinRoute("/my-football?tab=visited", null, true)} className="tt-action tt-action-secondary inline-flex min-h-11 items-center px-4 text-xs">SIGN IN</Link></div>
    </aside>}
  </main>;
}
