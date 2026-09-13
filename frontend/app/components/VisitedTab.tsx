"use client";

import axios from "axios";
import { apiErrorMessage } from "../../lib/api-error";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import api from "../../lib/api";
import type { GroundReview, MyGround } from "../types/grounds";
import MatchdayTips from "./MatchdayTips";
import { groundTimeframes, groundsInTimeframe, type GroundTimeframe } from "../../lib/my-grounds";

const PersonalGroundMap = dynamic(() => import("./PersonalGroundMap"), { ssr: false });

type VenueResult = { venue_id: number; name: string; city: string | null };
type FixtureCandidate = { fixture_id: number; fixture_date: string; home_team: string; away_team: string; league_name: string };

const reviewLabel = (review: GroundReview | null) =>
  !review || review.state === "blank" ? "Rate this ground" : review.state === "partial" ? "Continue review" : "Edit my review";

const knownDate = (value: string | null) => {
  if (!value) return "Unknown";
  const date = new Date(`${value}T00:00:00`);
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
};

export default function VisitedTab() {
  const requestedReview = useSearchParams().get("review");
  const [grounds, setGrounds] = useState<MyGround[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<VenueResult[]>([]);
  const [selected, setSelected] = useState<VenueResult | null>(null);
  const [visitDate, setVisitDate] = useState("");
  const [saving, setSaving] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [pastMatchDate, setPastMatchDate] = useState("");
  const [fixtureCandidates, setFixtureCandidates] = useState<FixtureCandidate[]>([]);
  const [findingMatches, setFindingMatches] = useState(false);
  const [editingVisitId, setEditingVisitId] = useState<number | null>(null);
  const [timeframe, setTimeframe] = useState<GroundTimeframe>("lifetime");
  const [reviewingId, setReviewingId] = useState<number | null>(null);
  const [showAddGround, setShowAddGround] = useState(false);
  const [scores, setScores] = useState({ atmosphere: null as number | null, pubs: null as number | null, travel: null as number | null, facilities: null as number | null, recommend: null as boolean | null });

  const loadGrounds = useCallback(async () => {
    await api.get("/session");
    const response = await api.get("/my-grounds");
    const loaded = response.data as MyGround[];
    setGrounds(loaded);
    return loaded;
  }, []);

  const showReview = (ground: MyGround) => {
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
    // The state update happens after the session/API promises resolve.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadGrounds().then((loaded) => {
      const ground = loaded.find((item) => item.venue_id === Number(requestedReview));
      if (requestedReview && ground) void openReview(ground);
    }).catch(() => setError("Unable to load My Grounds.")).finally(() => setLoading(false));
  }, [loadGrounds, openReview, requestedReview]);

  const search = async () => {
    if (query.trim().length < 2) return;
    setSearching(true); setError("");
    try { setResults((await api.get("/venues/search", { params: { q: query.trim(), limit: 20 } })).data); }
    catch { setError("Unable to search for grounds."); }
    finally { setSearching(false); }
  };

  const addVisit = async (venueId: number, date: string, done: () => void) => {
    if (saving) return;
    setSaving(true); setError("");
    try { await api.post(`/venues/${venueId}/visits`, { visit_date: date || null }); await loadGrounds(); done(); }
    catch (requestError) { setError(apiErrorMessage(requestError, "Unable to record this visit.")); }
    finally { setSaving(false); }
  };

  const submitReview = async () => {
    if (reviewingId === null || saving) return;
    setSaving(true); setError("");
    try {
      await api.patch(`/venues/${reviewingId}/away-day-reviews`, { recommend: scores.recommend, atmosphere_score: scores.atmosphere, pubs_score: scores.pubs, getting_there_score: scores.travel, facilities_score: scores.facilities });
      await loadGrounds(); setReviewingId(null);
    } catch (requestError) { setError(apiErrorMessage(requestError, "Unable to save your review.")); }
    finally { setSaving(false); }
  };

  const findPastMatches = async (venueId: number, date = pastMatchDate) => {
    if (!date || findingMatches) return;
    setFindingMatches(true); setError(""); setFixtureCandidates([]);
    try {
      const response = await api.get(`/venues/${venueId}/fixtures`, { params: { around_date: date, days: 7 } });
      setFixtureCandidates(response.data);
    } catch (requestError) {
      setError(apiErrorMessage(requestError, "Unable to find likely matches."));
    } finally { setFindingMatches(false); }
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
    if (!selected || saving) return;
    setSaving(true); setError("");
    try {
      await api.post(`/venues/${selected.venue_id}/visits`, { visit_date: visitDate || null, fixture_id: fixtureId });
      await loadGrounds(); setSelected(null); setVisitDate(""); setQuery(""); setResults([]); setFixtureCandidates([]);
    } catch (requestError) { setError(apiErrorMessage(requestError, "Unable to add this matchday.")); }
    finally { setSaving(false); }
  };

  const enteredScores = [scores.atmosphere, scores.pubs, scores.travel, scores.facilities].filter((score): score is number => score !== null);
  const overall = enteredScores.length ? (enteredScores.reduce((sum, score) => sum + score, 0) / enteredScores.length).toFixed(1) : "—";
  const visibleGrounds = useMemo(() => groundsInTimeframe(grounds, timeframe), [grounds, timeframe]);
  const cityCount = new Set(visibleGrounds.flatMap((ground) => ground.venue_city ? [ground.venue_city.trim().toLocaleLowerCase()] : [])).size;
  const countryCount = new Set(visibleGrounds.flatMap((ground) => ground.venue_country ? [ground.venue_country.trim().toLocaleLowerCase()] : [])).size;
  const matchdayCount = visibleGrounds.reduce((total, ground) => total + ground.visit_count, 0);
  const unplottableCount = visibleGrounds.filter((ground) => ground.latitude === null || ground.longitude === null).length;

  const renderReviewPanel = (ground: MyGround) => <section className="mt-5 border-t-2 border-[var(--tt-ink)] pt-5" aria-labelledby={`review-heading-${ground.venue_id}`}>
    <p className="tt-kicker">Your verdict</p>
    <h3 id={`review-heading-${ground.venue_id}`} className="tt-display mt-1 text-4xl leading-none">{reviewLabel(ground.review)}</h3>
    <p className="mt-2 text-[var(--tt-muted)]">Your review is one opinion of the ground and remains separate from your visit history.</p>
    <div className="mt-5 bg-[var(--tt-newsprint)] p-4 sm:p-5"><p className="tt-display text-4xl text-[var(--brand-interactive)]">{overall} / 10</p><div className="mt-5 grid gap-5 sm:grid-cols-2">{([['Atmosphere','atmosphere'],['Pubs & food','pubs'],['Getting there','travel'],['Stadium experience','facilities']] as const).map(([label,key]) => <fieldset key={key}><legend className="tt-kicker">{label}</legend><div className="mt-2 flex flex-wrap gap-1">{[1,2,3,4,5,6,7,8,9,10].map((score) => <button key={score} type="button" aria-pressed={scores[key] === score} onClick={() => setScores((current) => ({ ...current, [key]: score }))} className={`min-h-10 min-w-10 border-2 border-[var(--tt-ink)] text-sm font-bold ${scores[key] === score ? "bg-[var(--brand-interactive)] text-[var(--tt-paper)]" : "bg-[var(--tt-paper)]"}`}>{score}</button>)}</div></fieldset>)}</div><fieldset className="mt-6"><legend className="tt-kicker">Would you recommend this ground?</legend><div className="mt-2 flex gap-2"><button type="button" onClick={() => setScores((current) => ({...current,recommend:true}))} className={`tt-action px-5 ${scores.recommend === true ? "" : "tt-action-secondary"}`}>Yes</button><button type="button" onClick={() => setScores((current) => ({...current,recommend:false}))} className={`tt-action px-5 ${scores.recommend === false ? "" : "tt-action-secondary"}`}>No</button></div></fieldset>
      <MatchdayTips venueId={ground.venue_id} inline />
      <div className="mt-6 flex flex-wrap gap-3"><button type="button" onClick={() => setReviewingId(null)} className="tt-action tt-action-secondary px-5">Maybe later</button><button type="button" disabled={saving || (scores.recommend === null && enteredScores.length === 0)} onClick={() => void submitReview()} className="tt-action px-5">{saving ? "Saving…" : "Save review"}</button></div>
    </div>
  </section>;

  return <main className="mx-auto w-full max-w-5xl px-4 py-4 sm:px-6 sm:py-8">
    <header className="border-b-2 border-[var(--tt-ink)] pb-3"><h1 className="tt-display text-4xl leading-none sm:text-5xl">My football world</h1><p className="mt-2 text-sm text-[var(--tt-muted)]">Where football has taken you.</p></header>
    {!loading && grounds.length > 0 && <button type="button" onClick={() => setShowAddGround((current) => !current)} aria-expanded={showAddGround} aria-controls="add-ground" className="tt-action tt-action-secondary mt-4 inline-flex h-11 items-center justify-center whitespace-nowrap px-4 text-xs">{showAddGround ? "Close add ground" : "+ Add a ground"}</button>}
    {error && <p role="alert" className="mt-5 border-l-4 border-red-700 bg-[var(--tt-paper)] px-4 py-3 font-semibold text-red-800">{error}</p>}
    {loading && <p className="mt-6 font-semibold">Loading your ground history…</p>}
    {!loading && grounds.length === 0 && <section className="mt-8 border-y-2 border-[var(--tt-ink)] py-8"><p className="tt-display text-3xl">No grounds recorded yet.</p><p className="mt-2 text-[var(--tt-muted)]">Add somewhere you&apos;ve been.</p></section>}

    {!loading && grounds.length > 0 && <section className="mt-5" aria-labelledby="football-map-heading"><h2 id="football-map-heading" className="sr-only">My football world map</h2><div className="mb-4 inline-flex max-w-full overflow-x-auto border-b border-[var(--tt-rule)]" aria-label="Show visits from">{groundTimeframes.map((option) => <button key={option.key} type="button" aria-pressed={timeframe === option.key} onClick={() => setTimeframe(option.key)} className={`min-h-11 shrink-0 border-b-2 px-3 text-[0.68rem] font-extrabold uppercase tracking-[0.06em] ${timeframe === option.key ? "border-[var(--brand-interactive)] text-[var(--brand-interactive)]" : "border-transparent text-[var(--tt-muted)]"}`}>{option.label}</button>)}</div><p className="mb-3 text-xs font-extrabold uppercase tracking-[0.09em] text-[var(--brand-interactive)]">{visibleGrounds.length} grounds{cityCount > 0 ? ` · ${cityCount} cities` : ""}{countryCount > 0 ? ` · ${countryCount} countries` : ""} · {matchdayCount} matchdays</p>{visibleGrounds.length > 0 ? <PersonalGroundMap grounds={visibleGrounds}/> : <div className="border-y-2 border-[var(--tt-ink)] py-6"><p className="font-bold">No visits in this timeframe.</p><p className="mt-1 text-sm text-[var(--tt-muted)]">Try a longer timeframe.</p></div>}{unplottableCount > 0 && <p className="mt-2 text-xs font-bold text-[var(--tt-muted)]">{unplottableCount} visited {unplottableCount === 1 ? "ground could" : "grounds could"} not be plotted because coordinates are unavailable.</p>}</section>}

    {!loading && visibleGrounds.length > 0 && <section className="mt-7 border-t-2 border-[var(--tt-ink)] pt-3" aria-labelledby="grounds-list-heading"><h2 id="grounds-list-heading" className="tt-display text-3xl leading-none sm:text-4xl">The grounds you know</h2><div className="mt-4 grid gap-3 sm:grid-cols-2">{visibleGrounds.map((ground) => <article key={ground.venue_id} className={`tt-panel flex min-w-0 flex-col p-4 ${reviewingId === ground.venue_id ? "sm:col-span-2" : ""}`}>
      <h2 className="tt-display break-words text-[1.7rem] leading-[0.94]">{ground.venue_name}</h2><p className="mt-1 text-xs font-bold uppercase tracking-[0.08em] text-[var(--tt-muted)]">{[ground.venue_city, ground.venue_country].filter(Boolean).join(" · ")}</p>
      <p className="mt-3 text-sm font-bold text-[var(--tt-muted)]">{ground.latest_visit_date ? `Last there · ${knownDate(ground.latest_visit_date)}` : "Date not remembered"}</p>
      <div className="mt-2"><Link href={`/venue/${ground.venue_id}`} className="inline-flex min-h-11 items-center text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)] underline decoration-2 underline-offset-4">View ground →</Link></div>
      {reviewingId === ground.venue_id && renderReviewPanel(ground)}
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 border-t border-[var(--tt-rule)] pt-1 text-xs font-extrabold uppercase tracking-[0.08em]"><button type="button" onClick={() => setExpandedId(expandedId === ground.venue_id ? null : ground.venue_id)} className="min-h-11 text-[var(--tt-muted)] underline decoration-2 underline-offset-4">{expandedId === ground.venue_id ? "Hide visits" : "Visit details"}</button></div>
      {expandedId === ground.venue_id && <ul className="mt-4 border-t border-[var(--tt-rule)] pt-3">{ground.visits.map((visit) => { const fixture = ground.attended_fixtures.find((item) => item.fixture_id === visit.fixture_id); return <li key={visit.visit_id} className="border-b border-[var(--tt-rule)] py-3 last:border-0"><p className="text-xs font-bold uppercase tracking-[0.08em] text-[var(--tt-muted)]">{visit.visit_date ? knownDate(visit.visit_date) : "Date not remembered"}</p>{fixture && <><p className="mt-1 font-bold">{fixture.home_team} v {fixture.away_team}</p><p className="mt-1 text-sm text-[var(--tt-muted)]">{fixture.league_name}</p></>}{fixture && <Link href={`/fixture/${fixture.fixture_id}`} className="mt-1 inline-flex min-h-10 items-center text-xs font-extrabold uppercase text-[var(--brand-interactive)] underline">View match →</Link>}<button type="button" onClick={() => { setEditingVisitId(visit.visit_id); setPastMatchDate(visit.visit_date ?? ""); setFixtureCandidates([]); }} className="ml-4 min-h-10 text-xs font-extrabold uppercase text-[var(--brand-interactive)] underline">{fixture ? "Change match" : "Attach match"}</button>{fixture && <button type="button" disabled={saving} onClick={() => void updateVisitFixture(ground, visit.visit_id, null)} className="ml-4 min-h-10 text-xs font-extrabold uppercase text-[var(--tt-muted)] underline">Remove link</button>}{editingVisitId === visit.visit_id && <div className="mt-2"><div className="flex flex-wrap gap-2"><input type="date" aria-label="Visit date" value={pastMatchDate} onChange={(event) => { setPastMatchDate(event.target.value); setFixtureCandidates([]); }} className="tt-control px-3"/><button type="button" disabled={!pastMatchDate || findingMatches} onClick={() => void findPastMatches(ground.venue_id)} className="tt-action px-3">Find matches</button></div>{fixtureCandidates.map((candidate) => <button key={candidate.fixture_id} type="button" disabled={saving} onClick={() => void updateVisitFixture(ground, visit.visit_id, candidate.fixture_id)} className="mt-2 block min-h-10 text-left font-bold text-[var(--brand-interactive)] underline">{candidate.home_team} v {candidate.away_team} · {knownDate(candidate.fixture_date.slice(0, 10))}</button>)}</div>}</li>; })}</ul>}
    </article>)}</div></section>}

    {!loading && (grounds.length === 0 || showAddGround) && <section id="add-ground" className="mt-8 border-t-2 border-[var(--tt-ink)] pt-3" aria-labelledby="add-ground-heading"><h2 id="add-ground-heading" className="tt-display text-3xl leading-none sm:text-4xl">Add a ground</h2>{grounds.length > 0 && <p className="mt-1 text-sm text-[var(--tt-muted)]">Add somewhere you&apos;ve been.</p>}<div className="mt-4 flex flex-wrap gap-2"><label htmlFor="ground-search" className="sr-only">Search for a ground or city</label><input id="ground-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void search(); }} placeholder="Search ground or city" className="tt-control min-w-0 flex-1 px-4"/><button type="button" disabled={searching || query.trim().length < 2} onClick={() => void search()} className="tt-action px-5">{searching ? "Searching…" : "Search"}</button></div>
      {!selected && results.length > 0 && <div className="tt-panel mt-4 divide-y divide-[var(--tt-rule)]">{results.map((venue) => <button key={venue.venue_id} type="button" onClick={() => setSelected(venue)} className="block min-h-12 w-full px-4 py-3 text-left hover:bg-[var(--tt-paper)]"><strong>{venue.name}</strong>{venue.city && <span className="ml-2 text-[var(--tt-muted)]">{venue.city}</span>}{grounds.some((ground) => ground.venue_id === venue.venue_id) && <span className="ml-2 text-xs font-bold uppercase text-[var(--brand-interactive)]">Already visited</span>}</button>)}</div>}
      {selected && <div className="tt-panel mt-4 p-5"><p className="tt-display break-words text-3xl">{selected.name}</p>{selected.city && <p className="break-words text-[var(--tt-muted)]">{selected.city}</p>}<label htmlFor="new-visit-date" className="tt-kicker mt-4 block">Visit date (optional)</label><input id="new-visit-date" type="date" value={visitDate} onChange={(event) => { setVisitDate(event.target.value); setFixtureCandidates([]); }} className="tt-control mt-2 px-3"/>{visitDate && <button type="button" disabled={findingMatches} onClick={() => void findPastMatches(selected.venue_id, visitDate)} className="ml-2 min-h-11 text-xs font-extrabold uppercase text-[var(--brand-interactive)] underline">Find the match</button>}{fixtureCandidates.length > 0 && <div className="mt-3">{fixtureCandidates.map((fixture) => <button key={fixture.fixture_id} type="button" disabled={saving} onClick={() => void recordSelectedFixture(fixture.fixture_id)} className="block min-h-11 w-full border-t border-[var(--tt-rule)] py-2 text-left font-bold text-[var(--brand-interactive)]">{fixture.home_team} v {fixture.away_team} · {knownDate(fixture.fixture_date.slice(0, 10))}</button>)}</div>}<div className="mt-4 flex flex-wrap gap-3"><button type="button" onClick={() => setSelected(null)} className="tt-action tt-action-secondary px-4">Change ground</button><button type="button" disabled={saving || (grounds.some((ground) => ground.venue_id === selected.venue_id) && !visitDate)} onClick={() => void addVisit(selected.venue_id, visitDate, () => { setSelected(null); setVisitDate(""); setQuery(""); setResults([]); setFixtureCandidates([]); })} className="tt-action px-4">{saving ? "Adding…" : fixtureCandidates.length > 0 ? "Add without a match" : grounds.some((ground) => ground.venue_id === selected.venue_id) ? "Add another visit" : "Add to My Grounds"}</button></div></div>}
    </section>}
  </main>;
}
