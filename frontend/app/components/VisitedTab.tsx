"use client";

import axios from "axios";
import { apiErrorMessage } from "../../lib/api-error";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import api from "../../lib/api";
import type { GroundReview, MyGround } from "../types/grounds";
import FixtureTeams from "./FixtureTeams";
import MatchdayTips from "./MatchdayTips";

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
  const [visitSuccess, setVisitSuccess] = useState<{ venueId: number; message: string } | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [pastMatchId, setPastMatchId] = useState<number | null>(null);
  const [pastMatchDate, setPastMatchDate] = useState("");
  const [fixtureCandidates, setFixtureCandidates] = useState<FixtureCandidate[]>([]);
  const [findingMatches, setFindingMatches] = useState(false);
  const [reviewingId, setReviewingId] = useState<number | null>(null);
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
    setSaving(true); setError(""); setVisitSuccess(null);
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
    setSaving(true); setError(""); setVisitSuccess(null);
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

  const findPastMatches = async (venueId: number) => {
    if (!pastMatchDate || findingMatches) return;
    setFindingMatches(true); setError(""); setFixtureCandidates([]);
    try {
      const response = await api.get(`/venues/${venueId}/fixtures`, { params: { around_date: pastMatchDate, days: 7 } });
      setFixtureCandidates(response.data);
    } catch (requestError) {
      setError(apiErrorMessage(requestError, "Unable to find likely matches."));
    } finally { setFindingMatches(false); }
  };

  const recordPastFixture = async (venueId: number, fixtureId: number) => {
    if (saving) return;
    setSaving(true); setError(""); setVisitSuccess(null);
    try {
      const response = await api.post(`/venues/${venueId}/visits`, { fixture_id: fixtureId });
      if (response.data.fixture_id !== fixtureId) throw new Error("Selected fixture was not attached to attendance");
      await loadGrounds();
      setPastMatchId(null); setPastMatchDate(""); setFixtureCandidates([]);
      setVisitSuccess({ venueId, message: "Visit added with match details" });
    } catch (requestError) {
      setError(apiErrorMessage(requestError, "Unable to add this past match."));
    } finally { setSaving(false); }
  };

  const enteredScores = [scores.atmosphere, scores.pubs, scores.travel, scores.facilities].filter((score): score is number => score !== null);
  const overall = enteredScores.length ? (enteredScores.reduce((sum, score) => sum + score, 0) / enteredScores.length).toFixed(1) : "—";
  const cityCount = new Set(grounds.flatMap((ground) => ground.venue_city ? [ground.venue_city.trim().toLocaleLowerCase()] : [])).size;
  const countryCount = new Set(grounds.flatMap((ground) => ground.venue_country ? [ground.venue_country.trim().toLocaleLowerCase()] : [])).size;
  const matchdayCount = grounds.reduce((total, ground) => total + ground.visit_count, 0);
  const unplottableCount = grounds.filter((ground) => ground.latitude === null || ground.longitude === null).length;

  const renderReviewPanel = (ground: MyGround) => <section className="mt-5 border-t-2 border-[var(--tt-ink)] pt-5" aria-labelledby={`review-heading-${ground.venue_id}`}>
    <p className="tt-kicker">Your verdict</p>
    <h3 id={`review-heading-${ground.venue_id}`} className="tt-display mt-1 text-4xl leading-none">{reviewLabel(ground.review)}</h3>
    <p className="mt-2 text-[var(--tt-muted)]">Your review is one opinion of the ground and remains separate from your visit history.</p>
    <div className="mt-5 bg-[var(--tt-newsprint)] p-4 sm:p-5"><p className="tt-display text-4xl text-[var(--tt-blue)]">{overall} / 10</p><div className="mt-5 grid gap-5 sm:grid-cols-2">{([['Atmosphere','atmosphere'],['Pubs & food','pubs'],['Getting there','travel'],['Stadium experience','facilities']] as const).map(([label,key]) => <fieldset key={key}><legend className="tt-kicker">{label}</legend><div className="mt-2 flex flex-wrap gap-1">{[1,2,3,4,5,6,7,8,9,10].map((score) => <button key={score} type="button" aria-pressed={scores[key] === score} onClick={() => setScores((current) => ({ ...current, [key]: score }))} className={`min-h-10 min-w-10 border-2 border-[var(--tt-ink)] text-sm font-bold ${scores[key] === score ? "bg-[var(--tt-blue)] text-[var(--tt-paper)]" : "bg-[var(--tt-paper)]"}`}>{score}</button>)}</div></fieldset>)}</div><fieldset className="mt-6"><legend className="tt-kicker">Would you recommend this ground?</legend><div className="mt-2 flex gap-2"><button type="button" onClick={() => setScores((current) => ({...current,recommend:true}))} className={`tt-action px-5 ${scores.recommend === true ? "" : "tt-action-secondary"}`}>Yes</button><button type="button" onClick={() => setScores((current) => ({...current,recommend:false}))} className={`tt-action px-5 ${scores.recommend === false ? "" : "tt-action-secondary"}`}>No</button></div></fieldset>
      <MatchdayTips venueId={ground.venue_id} inline />
      <div className="mt-6 flex flex-wrap gap-3"><button type="button" onClick={() => setReviewingId(null)} className="tt-action tt-action-secondary px-5">Maybe later</button><button type="button" disabled={saving || (scores.recommend === null && enteredScores.length === 0)} onClick={() => void submitReview()} className="tt-action px-5">{saving ? "Saving…" : "Save review"}</button></div>
    </div>
  </section>;

  return <main className="mx-auto w-full max-w-5xl px-4 py-4 sm:px-6 sm:py-8">
    <header className="border-b-2 border-[var(--tt-ink)] pb-3"><h1 className="tt-display text-4xl leading-none sm:text-5xl">My football world</h1><p className="mt-2 text-sm text-[var(--tt-muted)]">Where football has taken you.</p></header>
    {error && <p role="alert" className="mt-5 border-l-4 border-red-700 bg-[var(--tt-paper)] px-4 py-3 font-semibold text-red-800">{error}</p>}
    {loading && <p className="mt-6 font-semibold">Loading your ground history…</p>}
    {!loading && grounds.length === 0 && <section className="mt-8 border-y-2 border-[var(--tt-ink)] py-8"><p className="tt-display text-3xl">No grounds recorded yet.</p><p className="mt-2 text-[var(--tt-muted)]">Search below to make your first ground one of yours.</p></section>}

    {!loading && grounds.length > 0 && <section className="mt-4" aria-labelledby="football-map-heading"><h2 id="football-map-heading" className="sr-only">My football world map</h2><p className="mb-3 text-xs font-extrabold uppercase tracking-[0.09em] text-[var(--tt-blue)]">{grounds.length} grounds{cityCount > 0 ? ` · ${cityCount} cities` : ""}{countryCount > 0 ? ` · ${countryCount} countries` : ""} · {matchdayCount} matchdays</p><PersonalGroundMap grounds={grounds}/>{unplottableCount > 0 && <p className="mt-2 text-xs font-bold text-[var(--tt-muted)]">{unplottableCount} visited {unplottableCount === 1 ? "ground could" : "grounds could"} not be plotted because coordinates are unavailable.</p>}</section>}

    {!loading && grounds.length > 0 && <section className="mt-7 border-t-2 border-[var(--tt-ink)] pt-3" aria-labelledby="grounds-list-heading"><h2 id="grounds-list-heading" className="tt-display text-3xl leading-none sm:text-4xl">The grounds you know</h2><div className="mt-4 grid gap-3 sm:grid-cols-2">{grounds.map((ground) => <article key={ground.venue_id} className={`tt-panel flex min-w-0 flex-col p-4 ${reviewingId === ground.venue_id ? "sm:col-span-2" : ""}`}>
      <h2 className="tt-display break-words text-3xl leading-[0.92]">{ground.venue_name}</h2><p className="mt-1 text-xs font-bold uppercase tracking-[0.08em] text-[var(--tt-muted)]">{[ground.venue_city, ground.venue_country].filter(Boolean).join(" · ")}</p>
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 border-y border-[var(--tt-rule)] py-3 text-xs"><div><dt className="font-extrabold uppercase tracking-[0.08em] text-[var(--tt-muted)]">Visits</dt><dd className="tt-display mt-0.5 text-2xl">{ground.visit_count}</dd></div>{ground.latest_visit_date ? <div><dt className="font-extrabold uppercase tracking-[0.08em] text-[var(--tt-muted)]">Latest</dt><dd className="mt-1 font-bold">{knownDate(ground.latest_visit_date)}</dd></div> : ground.has_undated_visit ? <div><dt className="font-extrabold uppercase tracking-[0.08em] text-[var(--tt-muted)]">Visit date</dt><dd className="mt-1 font-bold">Not remembered</dd></div> : null}<div><dt className="font-extrabold uppercase tracking-[0.08em] text-[var(--tt-muted)]">My rating</dt><dd className="tt-display mt-0.5 text-xl">{ground.review?.overall_score?.toFixed(1) ?? "—"}</dd></div><div><dt className="font-extrabold uppercase tracking-[0.08em] text-[var(--tt-muted)]">Terrace rating</dt><dd className="tt-display mt-0.5 text-xl">{ground.community_terrace_rating?.toFixed(1) ?? "—"}</dd></div></dl>
      <div className="mt-3"><Link href={`/venue/${ground.venue_id}`} className="tt-action inline-flex items-center px-4">View ground</Link></div>
      {reviewingId === ground.venue_id && renderReviewPanel(ground)}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 border-t border-[var(--tt-rule)] pt-2 text-xs font-extrabold uppercase tracking-[0.08em]"><button type="button" disabled={saving} onClick={() => void openReview(ground)} className="min-h-11 text-[var(--tt-blue)] underline decoration-2 underline-offset-4">{reviewLabel(ground.review)}</button><button type="button" onClick={() => { setPastMatchId(pastMatchId === ground.venue_id ? null : ground.venue_id); setPastMatchDate(""); setFixtureCandidates([]); }} className="min-h-11 text-[var(--tt-blue)] underline decoration-2 underline-offset-4">Add a visit →</button>{ground.attended_fixtures.length > 0 && <button type="button" onClick={() => setExpandedId(expandedId === ground.venue_id ? null : ground.venue_id)} className="min-h-11 text-[var(--tt-blue)] underline decoration-2 underline-offset-4">{expandedId === ground.venue_id ? "Hide matches" : `${ground.attended_fixtures.length} ${ground.attended_fixtures.length === 1 ? "match" : "matches"}`}</button>}</div>
      {visitSuccess?.venueId === ground.venue_id && <p role="status" className="mt-4 border-l-4 border-[var(--tt-blue)] bg-[var(--tt-newsprint)] px-3 py-2 text-sm font-bold uppercase tracking-[0.08em]">✓ {visitSuccess.message}</p>}
      {pastMatchId === ground.venue_id && <div className="mt-4 border-t border-[var(--tt-rule)] pt-4"><p className="tt-kicker">Add a visit</p><p className="mt-1 text-sm text-[var(--tt-muted)]">Choose the date you remember. We&apos;ll find the match details when we can.</p><div className="mt-3 flex flex-wrap gap-2"><label htmlFor={`past-match-${ground.venue_id}`} className="sr-only">Visit date</label><input id={`past-match-${ground.venue_id}`} type="date" value={pastMatchDate} onChange={(event) => { setPastMatchDate(event.target.value); setFixtureCandidates([]); }} className="tt-control px-3"/><button type="button" disabled={!pastMatchDate || findingMatches} onClick={() => void findPastMatches(ground.venue_id)} className="tt-action px-4">{findingMatches ? "Finding…" : "Continue / find match"}</button></div>{!ground.has_undated_visit && !pastMatchDate && <button type="button" disabled={saving} onClick={() => void addVisit(ground.venue_id, "", () => { setPastMatchId(null); setFixtureCandidates([]); setVisitSuccess({ venueId: ground.venue_id, message: "Visit added with date not remembered" }); })} className="mt-3 min-h-11 text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)] underline decoration-2 underline-offset-4">I don&apos;t remember the date</button>}{ground.has_undated_visit && !pastMatchDate && <p className="mt-3 text-xs text-[var(--tt-muted)]">You already have one visit here without a remembered date. Choose a date to add another.</p>}{fixtureCandidates.length > 0 && <div className="mt-4"><p className="tt-display text-2xl">Which game did you see?</p><div className="mt-3 grid gap-3">{fixtureCandidates.map((fixture) => <article key={fixture.fixture_id} className="border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] p-3"><div className="flex flex-wrap items-center justify-between gap-2"><p className="tt-kicker">{new Date(fixture.fixture_date).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}</p>{fixture.fixture_date.slice(0, 10) === pastMatchDate && <span className="bg-[var(--tt-blue)] px-2 py-1 text-[0.65rem] font-extrabold uppercase tracking-[0.1em] text-[var(--tt-paper)]">Exact date</span>}</div><FixtureTeams homeTeam={fixture.home_team} awayTeam={fixture.away_team} className="mt-2" teamClassName="text-2xl leading-none" separatorClassName="my-1 text-[0.65rem]"/><button type="button" disabled={saving} onClick={() => void recordPastFixture(ground.venue_id, fixture.fixture_id)} className="tt-action mt-3 px-4">This one</button></article>)}</div></div>}{pastMatchDate && !findingMatches && <button type="button" disabled={saving} onClick={() => void addVisit(ground.venue_id, pastMatchDate, () => { setPastMatchId(null); setPastMatchDate(""); setFixtureCandidates([]); setVisitSuccess({ venueId: ground.venue_id, message: "Visit added without match details" }); })} className="mt-4 min-h-11 text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)] underline decoration-2 underline-offset-4">I don&apos;t remember / none of these</button>}</div>}
      {expandedId === ground.venue_id && <ul className="mt-4 border-t border-[var(--tt-rule)] pt-3">{ground.attended_fixtures.map((fixture) => <li key={fixture.fixture_id} className="border-b border-[var(--tt-rule)] py-3 last:border-0"><Link href={`/fixture/${fixture.fixture_id}`} className="font-bold hover:text-[var(--tt-blue)]">{fixture.home_team} vs {fixture.away_team}</Link><p className="mt-1 text-xs text-[var(--tt-muted)]">{new Date(fixture.fixture_date).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</p></li>)}</ul>}
    </article>)}</div></section>}

    <section className="mt-8 border-t-2 border-[var(--tt-ink)] pt-3" aria-labelledby="add-ground-heading"><h2 id="add-ground-heading" className="tt-display text-3xl leading-none sm:text-4xl">Add a ground</h2><p className="mt-1 text-sm text-[var(--tt-muted)]">Add somewhere you&apos;ve been. A review is optional.</p><div className="mt-4 flex flex-wrap gap-2"><label htmlFor="ground-search" className="sr-only">Search for a ground or city</label><input id="ground-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void search(); }} placeholder="Search ground or city" className="tt-control min-w-0 flex-1 px-4"/><button type="button" disabled={searching || query.trim().length < 2} onClick={() => void search()} className="tt-action px-5">{searching ? "Searching…" : "Search"}</button></div>
      {!selected && results.length > 0 && <div className="tt-panel mt-4 divide-y divide-[var(--tt-rule)]">{results.map((venue) => <button key={venue.venue_id} type="button" onClick={() => setSelected(venue)} className="block min-h-12 w-full px-4 py-3 text-left hover:bg-[var(--tt-paper)]"><strong>{venue.name}</strong>{venue.city && <span className="ml-2 text-[var(--tt-muted)]">{venue.city}</span>}{grounds.some((ground) => ground.venue_id === venue.venue_id) && <span className="ml-2 text-xs font-bold uppercase text-[var(--tt-blue)]">Already visited</span>}</button>)}</div>}
      {selected && <div className="tt-panel mt-4 p-5"><p className="tt-display text-3xl">{selected.name}</p>{selected.city && <p className="text-[var(--tt-muted)]">{selected.city}</p>}<label htmlFor="new-visit-date" className="tt-kicker mt-4 block">Visit date {grounds.some((ground) => ground.venue_id === selected.venue_id) ? "" : "(optional)"}</label><input id="new-visit-date" type="date" value={visitDate} onChange={(event) => setVisitDate(event.target.value)} className="tt-control mt-2 px-3"/><div className="mt-4 flex flex-wrap gap-3"><button type="button" onClick={() => setSelected(null)} className="tt-action tt-action-secondary px-4">Change ground</button><button type="button" disabled={saving || (grounds.some((ground) => ground.venue_id === selected.venue_id) && !visitDate)} onClick={() => void addVisit(selected.venue_id, visitDate, () => { setSelected(null); setVisitDate(""); setQuery(""); setResults([]); })} className="tt-action px-4">{saving ? "Adding…" : grounds.some((ground) => ground.venue_id === selected.venue_id) ? "Add another visit" : "Add to My Grounds"}</button></div></div>}
    </section>
  </main>;
}
