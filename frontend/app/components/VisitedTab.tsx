"use client";

import axios from "axios";
import HistoryConfirmation from "./HistoryConfirmation";
import HistoryActionIcon from "./HistoryActionIcon";
import { PERSONAL_HISTORY_CHANGED } from "../../lib/personal-history";
import { localCalendarDateValue } from "../../lib/fixtureDiscovery";
import { useAuth } from "./AuthProvider";
import { accountRoute, signinRoute } from "../../lib/auth-flow";
import { eligibleAttendanceFixture, isFutureAttendanceDate, localAttendanceToday } from "../../lib/attendance-eligibility";
import { apiErrorMessage, emptyGuestHistory, historyLoadError } from "../../lib/api-error";
import dynamic from "next/dynamic";
import Link from "next/link";
import { scrollExpandedHeading } from "../../lib/navigation-scroll";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import api from "../../lib/api";
import type { FootprintSummary, GroundReview, MyGround, MyGroundFootprint } from "../types/grounds";
import MatchdayTips from "./MatchdayTips";
import GroundPhotograph from "./GroundPhotograph";
import { footballCountry, footballPassport } from "../../lib/my-grounds";

import FootprintLeagues from "./FootprintLeagues";
import TeamBadge from "./TeamBadge";
import { footprintGrounds, type FootprintPeriod } from "../../lib/football-footprint";

const PersonalGroundMap = dynamic(() => import("./PersonalGroundMap"), { ssr: false });

type VenueResult = { venue_id: number; name: string; city: string | null };
type Removal = { kind: "matchday"; venueId: number; visitId: number; fixtureId: number | null; name: string } | { kind: "ground"; venueId: number; count: number; revision: string; name: string };
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
  const [removal, setRemoval] = useState<Removal | null>(null);
  const [removalError, setRemovalError] = useState("");
  const [historyNotice, setHistoryNotice] = useState("");
  const historyWrite = useRef(false);
  const historyRead = useRef(0);
  const [replacementGround, setReplacementGround] = useState<VenueResult | null>(null);
  const [replacementQuery, setReplacementQuery] = useState("");
  const [replacementResults, setReplacementResults] = useState<VenueResult[]>([]);
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
  const [matchLookupFailed, setMatchLookupFailed] = useState(false);
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
    const generation = ++historyRead.current;
    const session = await api.get("/session");
    if (emptyGuestHistory(session.data, authenticated, authIssue) && !historySeen.current) {
      setError(""); return [];
    }
    const response = await api.get<MyGroundFootprint | MyGround[]>("/my-grounds", { params: { footprint: true } });
    // Old-backend compatibility: keep Lifetime usable without inventing seasons.
    const loaded = Array.isArray(response.data) ? response.data : response.data.grounds;
    if (generation !== historyRead.current) return loaded;
    setFootprint(Array.isArray(response.data) ? null : response.data.footprint);
    setGrounds(loaded);
    if (loaded.length) historySeen.current = true;
    setError("");
    return loaded;
  }, [authenticated, authIssue]);

  useEffect(() => {
    const reads = historyRead;
    const refresh = () => { if (document.visibilityState === "visible" && !historyWrite.current) void loadGrounds().catch(() => setError("Unable to refresh your history. Try again.")); };
    window.addEventListener(PERSONAL_HISTORY_CHANGED, refresh);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => { reads.current++; window.removeEventListener(PERSONAL_HISTORY_CHANGED, refresh); window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, [loadGrounds]);

  const beginGroundRemoval = async (venueId: number) => {
    if (saving || historyWrite.current) return;
    const ground = grounds.find(item => item.venue_id === venueId);
    if (!ground) return;
    historyWrite.current = true; setSaving(true); setError(""); setRemovalError("");
    try {
      const { data } = await api.get(`/venues/${venueId}/collection-removal`);
      if (data.venue_id !== venueId || !Number.isInteger(data.matchday_count) || data.matchday_count < 0 || !/^[a-f0-9]{64}$/.test(data.revision)) throw new Error("Removal preview was not confirmed");
      setRemoval({ kind: "ground", venueId, name: ground.venue_name, count: data.matchday_count, revision: data.revision });
    } catch (requestError) { setError(apiErrorMessage(requestError, "Unable to check your matchdays. Nothing was removed.")); }
    finally { historyWrite.current = false; setSaving(false); }
  };

  const confirmRemoval = async () => {
    if (!removal || historyWrite.current) return;
    const target = removal;
    historyWrite.current = true; historyRead.current++; setSaving(true); setRemovalError("");
    let confirmed = false;
    try {
      const { data } = target.kind === "ground"
        ? await api.delete(`/venues/${target.venueId}/collection`, { params: { expected_revision: target.revision } })
        : await api.delete(`/venues/${target.venueId}/visits/${target.visitId}`, { params: { check_fixture: true, expected_fixture_id: target.fixtureId } });
      confirmed = true;
      setGrounds(current => current.flatMap(ground => {
        if (ground.venue_id !== target.venueId) return [ground];
        if (target.kind === "ground") return [];
        const visits = ground.visits.filter(visit => visit.visit_id !== target.visitId);
        const independentlySaved = ground.independently_saved || data.independent_ground_preserved;
        if (!visits.length && !independentlySaved) return [];
        const dates = visits.flatMap(visit => visit.visit_date ? [visit.visit_date] : []).sort();
        return [{ ...ground, independently_saved: independentlySaved, visits, visit_count: visits.length, first_visit_date: dates[0] ?? null, latest_visit_date: dates.at(-1) ?? null, has_undated_visit: visits.some(visit => visit.visit_date === null), attended_fixtures: ground.attended_fixtures.filter(fixture => fixture.fixture_id !== target.fixtureId) }];
      }));
      setRemoval(null); setEditingVisitId(null);
      setHistoryNotice(target.kind === "ground" ? `${target.name} and ${data.removed_matchdays ?? target.count} matchdays removed.` : "Matchday removed. Your other matchdays and independently saved grounds are kept.");
      await loadGrounds();
    } catch (requestError) {
      if (confirmed) setError("Your removal was saved, but your history could not refresh. Try refreshing before making another change.");
      else setRemovalError(apiErrorMessage(requestError, "Nothing was removed. Please try again."));
    } finally { historyWrite.current = false; setSaving(false); }
  };

  const searchReplacementGround = async () => {
    if (replacementQuery.trim().length < 2) return;
    try { setReplacementResults((await api.get("/venues/search", { params: { q: replacementQuery.trim(), limit: 20 } })).data); }
    catch { setError("Unable to search for a replacement ground."); }
  };

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
      setEditingVisitId(null); setPastMatchDate(""); setSelected(response.data); setShowAddGround(true);
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
      const saved = await api.post<{ visit_id: number }>(`/venues/${venueId}/visits`, { visit_date: date || null, collection_only: !date, calendar_utc_offset_minutes: -new Date().getTimezoneOffset() });
      historySeen.current = true;
      const loaded = await loadGrounds();
      if (!Number.isInteger(saved.data.visit_id) || !loaded.some(ground => ground.venue_id === venueId && (date ? ground.visits.some(visit => visit.visit_id === saved.data.visit_id) : ground.independently_saved))) throw new Error("Visit persistence not confirmed");
      done();
    }
    catch (requestError) { setError(historyLoadError(requestError, "Your visit could not be confirmed. Check your history before trying again.")); }
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

  const findPastMatches = useCallback(async (venueId: number, date: string) => {
    if (!date || isFutureAttendanceDate(date)) return;
    const request = ++matchSearch.current;
    setFindingMatches(true); setMatchLookupFailed(false); setError(""); setFixtureCandidates([]); setSearchedMatchDate("");
    try {
      const response = await api.get(`/venues/${venueId}/fixtures`, { params: { around_date: date, days: 7, calendar_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone } });
      if (request !== matchSearch.current) return;
      setFixtureCandidates(response.data.filter((fixture: FixtureCandidate) => eligibleAttendanceFixture(fixture, venueId)));
      setSearchedMatchDate(date);
    } catch (requestError) {
      if (request === matchSearch.current) { setMatchLookupFailed(true); setError(apiErrorMessage(requestError, "Unable to find likely matches.")); }
    } finally { if (request === matchSearch.current) setFindingMatches(false); }
  }, []);

  const lookupVenueId = selected?.venue_id ?? replacementGround?.venue_id ?? grounds.find(ground => ground.visits.some(visit => visit.visit_id === editingVisitId))?.venue_id;
  const lookupDate = selected ? visitDate : pastMatchDate;
  useEffect(() => {
    if (!lookupVenueId || !lookupDate || isFutureAttendanceDate(lookupDate)) return;
    const timer = window.setTimeout(() => { void findPastMatches(lookupVenueId, lookupDate); }, 350);
    return () => { window.clearTimeout(timer); matchSearch.current += 1; };
  }, [lookupVenueId, lookupDate, findPastMatches]);

  const updateManualDate = async (ground: MyGround, visitId: number, date: string, fixtureId: number | null = null) => {
    if (saving || isFutureAttendanceDate(date) || !ground.visits.some(visit => visit.visit_id === visitId && visit.fixture_id === null)) return;
    setSaving(true); setError("");
    try {
      const response = await api.patch(`/venues/${ground.venue_id}/visits/${visitId}`, { visit_date: date || null, calendar_utc_offset_minutes: -new Date().getTimezoneOffset(), ...(fixtureId !== null ? { fixture_id: fixtureId } : {}) });
      const loaded = await loadGrounds();
      const visit = loaded.find(item => item.venue_id === ground.venue_id)?.visits.find(item => item.visit_id === visitId);
      if (response.data.visit_id !== visitId || !visit || visit.fixture_id !== fixtureId || visit.visit_date !== (date || null)) throw new Error("Date persistence not confirmed");
      setReplacementGround(null); setEditingVisitId(null); matchSearch.current += 1; setFindingMatches(false); setMatchLookupFailed(false); setFixtureCandidates([]); setPastMatchDate("");
    } catch (requestError) { setError(apiErrorMessage(requestError, "Your date change could not be confirmed. Check your history before trying again.")); }
    finally { setSaving(false); }
  };

  const updateVisitFixture = async (ground: MyGround, visitId: number, fixtureId: number | null) => {
    if (saving) return;
    setSaving(true); setError("");
    try {
      const { data } = await api.patch(`/venues/${ground.venue_id}/visits/${visitId}`, { fixture_id: fixtureId, allow_ground_change: true });
      if (data.visit_id !== visitId || data.fixture_id !== fixtureId || data.venue_id !== (replacementGround?.venue_id ?? ground.venue_id)) throw new Error("The changed match was not confirmed");
      setHistoryNotice("Match changed. My Grounds and My Matchdays are up to date.");
      await loadGrounds(); setReplacementGround(null); setEditingVisitId(null); matchSearch.current += 1; setFindingMatches(false); setMatchLookupFailed(false); setFixtureCandidates([]); setPastMatchDate("");
    } catch (requestError) { setError(apiErrorMessage(requestError, "Unable to update this visit.")); }
    finally { setSaving(false); }
  };

  const recordSelectedFixture = async (fixtureId: number) => {
    if (!selected || saving || isFutureAttendanceDate(visitDate)) return;
    setSaving(true); setError("");
    try {
      const saved = await api.post<{ visit_id: number }>(`/venues/${selected.venue_id}/visits`, { fixture_id: fixtureId });
      historySeen.current = true;
      const loaded = await loadGrounds();
      if (!Number.isInteger(saved.data.visit_id) || !loaded.some(ground => ground.venue_id === selected.venue_id && ground.visits.some(visit => visit.visit_id === saved.data.visit_id && visit.fixture_id === fixtureId))) throw new Error("Visit persistence not confirmed");
      setSelected(null); matchSearch.current += 1; setFindingMatches(false); setMatchLookupFailed(false); setVisitDate(""); setQuery(""); setResults([]); setFixtureCandidates([]);
    } catch (requestError) { setError(historyLoadError(requestError, "Your visit could not be confirmed. Check your history before trying again.")); }
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

  const renderFixtureCandidates = () => fixtureCandidates.length > 0 && <div className="mt-3">
    <h4 className="tt-kicker">MATCHES AROUND YOUR DATE</h4>
    {fixtureCandidates.map(fixture => <button key={fixture.fixture_id} type="button" aria-pressed={selectedFixtureId === fixture.fixture_id} disabled={saving} onClick={() => setSelectedFixtureId(selectedFixtureId === fixture.fixture_id ? null : fixture.fixture_id)} className={`mt-2 flex min-h-11 w-full items-start gap-2 border px-3 py-2 text-left text-sm font-bold text-[var(--brand-interactive)] ${selectedFixtureId === fixture.fixture_id ? "border-[var(--brand-interactive)] bg-[var(--mg-green-dark)]/5" : "border-[var(--tt-rule)]"}`}>
      <svg aria-hidden="true" viewBox="0 0 16 16" width="16" height="16" className="mt-0.5 shrink-0 border border-current" fill="none" stroke="currentColor" strokeWidth="2">{selectedFixtureId === fixture.fixture_id && <path d="m3 8 3 3 7-7" />}</svg>
      <span className="min-w-0 break-words">{fixture.home_team} v {fixture.away_team}<span className="mt-1 block text-xs font-normal">{knownDate(localCalendarDateValue(new Date(fixture.fixture_date)))}</span></span>
    </button>)}
  </div>;

  const editVisit = (venueId: number, visitId: number) => {
    setReplacementGround(null); setReplacementQuery(""); setReplacementResults([]);
    const visit = grounds.find(ground => ground.venue_id === venueId)?.visits.find(visit => visit.visit_id === visitId);
    if (!visit) return;
    matchSearch.current += 1; setFindingMatches(false); setMatchLookupFailed(false); setSearchedMatchDate("");
    setSelected(null); setVisitDate(""); setEditingVisitId(visit.visit_id); setSelectedFixtureId(null);
    const fixture = grounds.find(ground => ground.venue_id === venueId)?.attended_fixtures.find(item => item.fixture_id === visit.fixture_id);
    setPastMatchDate(fixture ? localCalendarDateValue(new Date(fixture.fixture_date)) : visit.visit_date ?? ""); setFixtureCandidates([]);
  };

  const renderVisitList = (ground: MyGround) => <><ul id={`ground-visits-${ground.venue_id}`} className="space-y-2">{ground.visits.map((visit) => { const fixture = ground.attended_fixtures.find((item) => item.fixture_id === visit.fixture_id); return <li key={visit.visit_id} className="border-t border-[var(--tt-rule)] py-2"><p className="text-xs font-bold uppercase tracking-[0.08em] text-[var(--tt-muted)]">{fixture ? knownDate(localCalendarDateValue(new Date(fixture.fixture_date))) : visit.visit_date ? knownDate(visit.visit_date) : "Date not recorded"}</p>{fixture && <><p className="mt-1 flex flex-wrap items-center gap-1 text-sm font-bold"><TeamBadge src={fixture.home_team_badge_url} className="h-5 w-5"/>{fixture.home_team}<span className="font-normal">v</span><TeamBadge src={fixture.away_team_badge_url} className="h-5 w-5"/>{fixture.away_team}</p><p className="mt-1 text-sm text-[var(--tt-muted)]">{fixture.league_name}</p></>}<div className="mt-2 grid gap-2">{visit.fixture_id !== null ? <>
        <Link href={`/fixture/${visit.fixture_id}`} className="tt-action inline-flex min-h-11 items-center justify-center px-3 text-xs">VIEW MATCH</Link>
        {editingVisitId !== visit.visit_id && <button type="button" disabled={saving} onClick={() => editVisit(ground.venue_id, visit.visit_id)} className="tt-action tt-action-secondary inline-flex min-h-11 items-center justify-center gap-2 px-3 text-xs"><HistoryActionIcon action="change"/>Change Match</button>}
      </> : editingVisitId !== visit.visit_id && <button type="button" onClick={() => editVisit(ground.venue_id, visit.visit_id)} className="tt-action tt-action-secondary inline-flex min-h-11 items-center justify-center gap-2 px-3 text-xs"><HistoryActionIcon action="change"/>Change Match</button>}
      <button type="button" disabled={saving} onClick={() => { setRemovalError(""); setRemoval({ kind: "matchday", venueId: ground.venue_id, visitId: visit.visit_id, fixtureId: visit.fixture_id, name: fixture ? `${fixture.home_team} vs ${fixture.away_team}` : ground.venue_name }); }} className="tt-action tt-action-secondary inline-flex min-h-11 items-center justify-center gap-2 px-3 text-xs"><HistoryActionIcon action="matchday"/>Remove Matchday</button>
      </div>{editingVisitId === visit.visit_id && <div className="mt-3">
        <h3 className="tt-kicker">{visit.fixture_id === null ? "EDIT VISIT" : "CHANGE MATCH"}</h3>
        <p className="mt-2 text-xs text-[var(--tt-muted)]">Changing the match keeps this matchday record. Photos attached to the old match will be unlinked.</p>
        <label htmlFor={`replacement-ground-${visit.visit_id}`} className="mt-3 block text-xs font-bold">Ground: {replacementGround?.name ?? ground.venue_name}</label>
        <div className="mt-1 flex gap-2"><input id={`replacement-ground-${visit.visit_id}`} type="search" value={replacementQuery} onChange={event => setReplacementQuery(event.target.value)} placeholder="Find another ground" className="tt-control min-w-0 flex-1 px-2"/><button type="button" disabled={saving || replacementQuery.trim().length < 2} onClick={() => void searchReplacementGround()} className="tt-action tt-action-secondary px-3">Search</button></div>
        {replacementResults.map(item => <button key={item.venue_id} type="button" onClick={() => { matchSearch.current++; setReplacementGround(item); setReplacementResults([]); setFixtureCandidates([]); setSelectedFixtureId(null); }} className="block min-h-11 w-full border-b border-[var(--tt-rule)] px-2 text-left text-sm font-bold">{item.name}{item.city ? `, ${item.city}` : ""}</button>)}
        <label className="mt-2 block text-xs font-bold" htmlFor={`edit-visit-date-${visit.visit_id}`}>Visit date</label>
        <input id={`edit-visit-date-${visit.visit_id}`} type="date" max={localAttendanceToday()} aria-label="Visit date" value={pastMatchDate} onChange={(event) => { matchSearch.current += 1; setFindingMatches(false); setMatchLookupFailed(false); setSearchedMatchDate(""); setPastMatchDate(event.target.value); setFixtureCandidates([]); setSelectedFixtureId(null); }} className="tt-control mt-1 max-w-full px-3"/>
        {findingMatches && <p role="status" className="mt-2 text-sm">Finding matches...</p>}
        {matchLookupFailed && <button type="button" onClick={() => void findPastMatches(replacementGround?.venue_id ?? ground.venue_id, pastMatchDate)} className="min-h-11 underline">Retry match search</button>}
        {pastMatchDate && searchedMatchDate === pastMatchDate && !findingMatches && fixtureCandidates.length === 0 && <p role="status" className="mt-2 text-sm">No eligible matches found nearby. You can keep your visit without a match link.</p>}
        {renderFixtureCandidates()}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button type="button" disabled={saving || isFutureAttendanceDate(pastMatchDate) || ((visit.fixture_id !== null || replacementGround !== null) && selectedFixtureId === null)} onClick={() => { if (selectedFixtureId !== null) void updateVisitFixture(ground, visit.visit_id, selectedFixtureId); else if (visit.fixture_id === null) void updateManualDate(ground, visit.visit_id, pastMatchDate); }} className="tt-action px-3">Save changes</button>
          <button type="button" disabled={saving} onClick={() => { setReplacementGround(null); setEditingVisitId(null); matchSearch.current += 1; setFindingMatches(false); setMatchLookupFailed(false); setPastMatchDate(""); setFixtureCandidates([]); setSelectedFixtureId(null); }} className="min-h-11 px-2 text-sm underline">Cancel</button>
        </div>
        {visit.fixture_id === null && visit.visit_date && <button type="button" disabled={saving} onClick={() => void updateManualDate(ground, visit.visit_id, "")} className="mt-2 min-h-11 text-xs font-bold uppercase text-[var(--tt-muted)] underline">Remove date</button>}
      </div>}</li>; })}</ul><button type="button" disabled={saving} onClick={() => void beginGroundRemoval(ground.venue_id)} className="tt-action tt-action-secondary mt-3 inline-flex min-h-11 w-full items-center justify-center gap-2 px-3 text-xs"><HistoryActionIcon action="ground"/>Remove Ground</button><p className="mt-2 text-xs leading-relaxed text-[var(--tt-muted)]">Removing the ground will also remove all {grounds.find(item => item.venue_id === ground.venue_id)?.visits.length ?? ground.visits.length} associated matchdays from My Matchdays.</p></>;

  const renderFootprintVisits = (projected: MyGround) => {
    // Use only original, owned records represented by this season projection.
    const owned = grounds.find(item => item.venue_id === projected.venue_id);
    if (!owned) return null;
    const ids = new Set(projected.visits.map(visit => visit.visit_id));
    return renderVisitList({ ...owned, visits: owned.visits.filter(visit => ids.has(visit.visit_id)) });
  };

  const renderGround = (ground: MyGround, nested: boolean) => <article key={ground.venue_id} className={`${nested ? "flex min-w-0 flex-col py-4" : "tt-panel flex min-w-0 flex-col p-4"} ${reviewingId === ground.venue_id ? "sm:col-span-2" : ""}`}>
      <h2 className="tt-display break-words text-[1.7rem] leading-[0.94]">{ground.venue_name}</h2><p className="mt-1 text-xs font-bold uppercase tracking-[0.08em] text-[var(--tt-muted)]">{[ground.venue_city, ground.venue_country].filter(Boolean).join(" · ")}</p>
      <p className="mt-3 text-xs font-extrabold uppercase tracking-[0.04em] text-[var(--brand-interactive)]">{ground.visit_count} {ground.visit_count === 1 ? "matchday" : "matchdays"}</p>
      <p className="mt-1 text-sm text-[var(--tt-muted)]">{ground.latest_visit_date ? `Last visited · ${knownDate(ground.latest_visit_date)}` : "Date not recorded"}</p>
      {Number(requestedReview) !== ground.venue_id && renderPersonalReview(ground, true)}
      <div className="mt-4 grid grid-cols-2 gap-2">
        <Link href={`/venue/${ground.venue_id}`} className="tt-action inline-flex min-w-0 items-center justify-center whitespace-nowrap px-1 text-center text-[0.68rem]! tracking-[0.04em]! sm:text-xs! focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">View ground →</Link>
        <button type="button" aria-expanded={expandedId === ground.venue_id} aria-controls={`ground-visits-${ground.venue_id}`} onClick={event => { if (expandedId !== ground.venue_id) scrollExpandedHeading(event.currentTarget); setExpandedId(expandedId === ground.venue_id ? null : ground.venue_id); }} className="tt-action tt-action-secondary min-w-0 whitespace-nowrap px-1 text-center text-[0.68rem]! tracking-[0.04em]! sm:text-xs! focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">{expandedId === ground.venue_id ? "Hide visits" : "Visit details"}</button>
      </div>
      {expandedId === ground.venue_id && renderVisitList(ground)}
    </article>;

  const recordForm = selected && <section id="record-matchday" aria-labelledby="record-matchday-heading" className="tt-panel mt-4 p-5">
    <h3 ref={recordHeading} tabIndex={-1} id="record-matchday-heading" className="tt-display text-3xl focus-visible:outline-2 focus-visible:outline-offset-2">Save your visit</h3>
    <p className="mt-2 font-bold break-words">{selected.name}</p>{selected.city && <p className="break-words text-[var(--tt-muted)]">{selected.city}</p>}
    <p className="mt-3 text-sm">Add this ground to your football passport. Enter a date to find the match you attended.</p>
    <label htmlFor="new-visit-date" className="tt-kicker mt-4 block">When did you visit? (optional)</label>
    <input id="new-visit-date" type="date" max={localAttendanceToday()} value={visitDate} onChange={event => { matchSearch.current += 1; setFindingMatches(false); setMatchLookupFailed(false); setSearchedMatchDate(""); setVisitDate(event.target.value); setFixtureCandidates([]); setSelectedFixtureId(null); }} className="tt-control mt-2 max-w-full px-3" />
    {findingMatches && <p role="status" className="mt-2 text-sm">Finding matches...</p>}
    {matchLookupFailed && <button type="button" onClick={() => void findPastMatches(selected.venue_id, visitDate)} className="min-h-11 underline">Retry match search</button>}
    {visitDate && searchedMatchDate === visitDate && !findingMatches && !isFutureAttendanceDate(visitDate) && fixtureCandidates.length === 0 && <div role="status" className="mt-3"><h4 className="font-extrabold">CAN&apos;T FIND YOUR MATCH?</h4><p className="mt-1 text-sm">You can still record your visit using the ground and date.</p></div>}
    {renderFixtureCandidates()}
    {isFutureAttendanceDate(visitDate) && <div role="status" className="mt-3 border-l-4 border-[var(--brand-interactive)] pl-3"><h4 className="font-extrabold">THAT MATCH HASN&apos;T HAPPENED YET</h4><p className="mt-1 text-sm">You can record your matchday once the game has been played.</p></div>}
    <div className="mt-4 grid grid-cols-2 gap-2">
      <button type="button" disabled={saving} onClick={() => { setSelected(null); matchSearch.current += 1; setFindingMatches(false); setMatchLookupFailed(false); setSelectedFixtureId(null); setFixtureCandidates([]); setVisitDate(""); window.requestAnimationFrame(() => document.getElementById("ground-search")?.focus()); }} className="tt-action tt-action-secondary min-w-0 px-2 text-xs">Change ground</button>
      <button type="button" disabled={saving || isFutureAttendanceDate(visitDate)} onClick={() => {
        if (selectedFixtureId !== null) void recordSelectedFixture(selectedFixtureId);
        else void addVisit(selected.venue_id, visitDate, () => { setSelected(null); matchSearch.current += 1; setFindingMatches(false); setMatchLookupFailed(false); setVisitDate(""); setQuery(""); setResults([]); setFixtureCandidates([]); });
      }} className="tt-action min-w-0 px-2 text-xs">{saving ? "Saving…" : "Save visit"}</button>
    </div>
  </section>;

  return <><HistoryConfirmation open={removal !== null} title={removal?.kind === "ground" ? `Remove ${removal.name}?` : "Remove this matchday?"} label={removal?.kind === "ground" ? "Remove Ground" : "Remove Matchday"} busy={saving} error={removalError}
    description={removal?.kind === "ground" ? `Remove ${removal.name} from My Grounds? This will also remove ${removal.count} ${removal.count === 1 ? "matchday" : "matchdays"} from My Matchdays, including any saved plans for those matches. Your ratings and other Interested fixtures are kept. Photos attached to removed matchdays will stop being shared.` : `Remove ${removal?.name ?? "this matchday"} from My Grounds and My Matchdays? Any saved plan for this match is removed too. Other matchdays and independently saved grounds are kept. Photos attached to this matchday will stop being shared.`}
    onCancel={() => { setRemoval(null); setRemovalError(""); }} onConfirm={() => void confirmRemoval()} /><main className="mx-auto w-full max-w-5xl px-4 py-4 sm:px-6 sm:py-8">
    {historyNotice && <p role="status" className="mb-4 border-l-4 border-[var(--brand-interactive)] p-3 text-sm font-bold">{historyNotice}</p>}
    <header className="border-b-2 border-[var(--tt-ink)] pb-3"><h1 className="tt-display text-4xl leading-none sm:text-5xl">My grounds</h1><p className="mt-2 text-sm text-[var(--tt-muted)]">Football takes you places.</p></header>
    {!loading && requestedReview && grounds.filter(ground => ground.venue_id === Number(requestedReview)).map(ground => <div key={ground.venue_id}>{renderPersonalReview(ground)}</div>)}
    {!loading && (selected !== null || grounds.length === 0 || showAddGround) && recordForm}
    {!loading && grounds.length > 0 && <button type="button" onClick={() => setShowAddGround((current) => !current)} aria-expanded={showAddGround} aria-controls="add-ground" className="tt-action tt-action-secondary mt-4 inline-flex h-11 items-center justify-center whitespace-nowrap px-4 text-xs">{showAddGround ? "Close add ground" : "+ Add a ground"}</button>}
    {!loading && !selected && grounds.length > 0 && showAddGround && <section id="add-ground" className="mt-8 border-t-2 border-[var(--tt-ink)] pt-3" aria-labelledby="add-ground-heading"><h2 id="add-ground-heading" className="tt-display text-3xl leading-none sm:text-4xl">Add a ground</h2>{grounds.length > 0 && <p className="mt-1 text-sm text-[var(--tt-muted)]">Add somewhere you&apos;ve been.</p>}<div className="mt-4 flex flex-wrap gap-2"><label htmlFor="ground-search" className="sr-only">Search for a ground or city</label><input id="ground-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void search(); }} placeholder="Search ground or city" className="tt-control min-w-0 flex-1 px-4"/><button type="button" disabled={searching || query.trim().length < 2} onClick={() => void search()} className="tt-action px-5">{searching ? "Searching…" : "Search"}</button></div>
      {!selected && results.length > 0 && <div className="tt-panel mt-4 divide-y divide-[var(--tt-rule)]">{results.map((venue) => <button key={venue.venue_id} type="button" onClick={() => { setEditingVisitId(null); setPastMatchDate(""); setSelected(venue); setSelectedFixtureId(null); setFixtureCandidates([]); }} className="block min-h-12 w-full px-4 py-3 text-left hover:bg-[var(--tt-paper)]"><strong>{venue.name}</strong>{venue.city && <span className="ml-2 text-[var(--tt-muted)]">{venue.city}</span>}{grounds.some((ground) => ground.venue_id === venue.venue_id) && <span className="ml-2 text-xs font-bold uppercase text-[var(--brand-interactive)]">Already visited</span>}</button>)}</div>}
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
            <h3><button type="button" aria-expanded={isOpen} aria-controls={panelId} onClick={event => { if (!isOpen) scrollExpandedHeading(event.currentTarget); setCollection(isOpen ? null : { country: country.key }); }} className="block min-h-11 w-full px-3 py-3 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">
              <span className="flex items-start justify-between gap-3"><span className="tt-display min-w-0 break-words text-2xl leading-none text-[var(--brand-interactive)]">{country.name}</span><span aria-hidden="true" className="shrink-0 text-[var(--brand-interactive)]">{isOpen ? "⌃" : "⌄"}</span></span>
              <span className="mt-2 block text-xs font-extrabold uppercase tracking-[0.04em]">{country.groundCount} {country.groundCount === 1 ? "ground" : "grounds"} · {country.matchdayCount} {country.matchdayCount === 1 ? "matchday" : "matchdays"}</span>
            </button></h3>
            {isOpen && <div id={panelId} className="mx-3 border-t border-[var(--tt-rule)] divide-y divide-[var(--tt-rule)]">{<FootprintLeagues key={`${country.key}-${timeframe}`} grounds={visibleGrounds.filter((ground) => footballCountry(ground.venue_country)?.key === country.key)} footprint={footprint} period={timeframe} renderVisits={renderFootprintVisits} />}</div>}
          </li>;
        })}
      </ul>
    </section>}

    {!loading && visibleGrounds.length > 0 && <div className="mt-5">
      <button type="button" aria-expanded={collection === "all"} aria-controls="all-ground-collection" onClick={event => { if (collection !== "all") scrollExpandedHeading(event.currentTarget); setCollection(collection === "all" ? null : "all"); }} className="tt-action tt-action-secondary min-h-11 px-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">{collection === "all" ? "Hide all grounds ↑" : "Show all grounds ↓"}</button>
      {collection === "all" && <section id="all-ground-collection" className="mt-5 border-t-2 border-[var(--tt-ink)] pt-3" aria-labelledby="grounds-list-heading"><h2 id="grounds-list-heading" className="tt-display text-3xl leading-none sm:text-4xl">The grounds you know</h2><div className="mt-4 grid gap-3 sm:grid-cols-2">{visibleGrounds.map((ground) => renderGround(ground, false))}</div></section>}
    </div>}

    {!loading && !selected && grounds.length === 0 && <section id="add-ground" className="mt-8 border-t-2 border-[var(--tt-ink)] pt-3" aria-labelledby="add-ground-heading"><h2 id="add-ground-heading" className="tt-display text-3xl leading-none sm:text-4xl">Add a ground</h2>{grounds.length > 0 && <p className="mt-1 text-sm text-[var(--tt-muted)]">Add somewhere you&apos;ve been.</p>}<div className="mt-4 flex flex-wrap gap-2"><label htmlFor="ground-search" className="sr-only">Search for a ground or city</label><input id="ground-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void search(); }} placeholder="Search ground or city" className="tt-control min-w-0 flex-1 px-4"/><button type="button" disabled={searching || query.trim().length < 2} onClick={() => void search()} className="tt-action px-5">{searching ? "Searching…" : "Search"}</button></div>
      {!selected && results.length > 0 && <div className="tt-panel mt-4 divide-y divide-[var(--tt-rule)]">{results.map((venue) => <button key={venue.venue_id} type="button" onClick={() => { setEditingVisitId(null); setPastMatchDate(""); setSelected(venue); setSelectedFixtureId(null); setFixtureCandidates([]); }} className="block min-h-12 w-full px-4 py-3 text-left hover:bg-[var(--tt-paper)]"><strong>{venue.name}</strong>{venue.city && <span className="ml-2 text-[var(--tt-muted)]">{venue.city}</span>}{grounds.some((ground) => ground.venue_id === venue.venue_id) && <span className="ml-2 text-xs font-bold uppercase text-[var(--brand-interactive)]">Already visited</span>}</button>)}</div>}
    </section>}
    {!authLoading && !authenticated && !authIssue && <aside aria-labelledby="guest-history-heading" className="mt-6 border-t border-[var(--tt-rule)] pt-4">
      <h2 id="guest-history-heading" className="tt-display text-2xl">KEEP YOUR FOOTBALL HISTORY</h2>
      <p className="mt-2 text-sm">Sign in or create an account to keep your grounds and matchdays saved.</p>
      <p className="mt-2 text-xs text-[var(--tt-muted)]">Your guest history is linked to this browser until you transfer it to your account. Clearing browser data or closing a private session can lose access.</p>
      <div className="mt-3 flex flex-wrap gap-3"><Link href={accountRoute("/signup", "/my-football?tab=visited")} className="tt-action inline-flex min-h-11 items-center px-4 text-xs">CREATE ACCOUNT</Link><Link href={signinRoute("/my-football?tab=visited", null, true)} className="tt-action tt-action-secondary inline-flex min-h-11 items-center px-4 text-xs">SIGN IN</Link></div>
    </aside>}
  </main></>;
}
