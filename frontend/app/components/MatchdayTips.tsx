"use client";

import { useEffect, useState } from "react";
import api from "../../lib/api";
import { apiErrorMessage } from "../../lib/api-error";

type Tip = { tip_id: number; venue_id: number; tip: string; helpful_votes: number; report_count: number; status: string; created_at: string };
type Props = { tips?: Tip[]; venueId: number; inline?: boolean };

export default function MatchdayTips({ tips = [], venueId, inline = false }: Props) {
  const [tipList, setTipList] = useState<Tip[]>(tips);
  const [showForm, setShowForm] = useState(false);
  const [newTip, setNewTip] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (inline) return;
    const openFromHash = () => {
      if (window.location.hash === "#tips-add") setShowForm(true);
    };
    openFromHash();
    window.addEventListener("hashchange", openFromHash);
    return () => window.removeEventListener("hashchange", openFromHash);
  }, [inline]);

  const toggleForm = () => {
    setShowForm((current) => !current);
    setError("");
    setSaved(false);
  };
  const markHelpful = async (tipId: number) => {
    try { const response = await api.post(`/tips/${tipId}/helpful`); setTipList((current) => current.map((tip) => tip.tip_id === tipId ? response.data : tip)); }
    catch (requestError) { setError(apiErrorMessage(requestError, "Could not mark that tip as helpful.")); }
  };
  const submitTip = async () => {
    const trimmed = newTip.trim();
    if (!trimmed) { setError("Please enter a tip before submitting."); return; }
    if (submitting) return;
    setSubmitting(true); setError(""); setSaved(false);
    try {
      const response = await api.post("/tips", { venue_id: venueId, tip: trimmed });
      setTipList((current) => [response.data, ...current]);
      setNewTip(""); setShowForm(false); setSaved(true);
    } catch (requestError) { setError(apiErrorMessage(requestError, "Could not submit your tip. Please try again.")); }
    finally { setSubmitting(false); }
  };

  const tipForm = showForm && <div className={`${inline ? "mt-3" : "tt-panel mt-5"} p-4`}><label htmlFor={`venue-tip-${venueId}-${inline ? "inline" : "section"}`} className="tt-kicker">Your matchday advice</label><textarea id={`venue-tip-${venueId}-${inline ? "inline" : "section"}`} value={newTip} onChange={(event) => setNewTip(event.target.value)} placeholder="Share useful advice for other supporters…" rows={4} className="tt-control mt-2 w-full resize-y p-3"/><div className="mt-3 flex flex-wrap gap-3"><button type="button" onClick={toggleForm} className="tt-action tt-action-secondary px-4">Cancel</button><button type="button" onClick={submitTip} disabled={submitting || !newTip.trim()} className="tt-action px-5">{submitting ? "Submitting…" : "Submit tip"}</button></div>{error && <p role="alert" className="mt-2 text-sm font-semibold text-red-800">{error}</p>}</div>;

  if (inline) {
    return <aside className="mt-6 border-y-2 border-[var(--tt-ink)] py-4"><p className="tt-display text-2xl">Got a tip for the next supporter?</p><p className="mt-1 text-sm text-[var(--tt-muted)]">Share something useful about pubs, transport, the away end, food or getting in/out.</p>{!showForm && <button type="button" onClick={toggleForm} className="mt-2 min-h-11 text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)] underline decoration-2 underline-offset-4">Add a tip →</button>}{tipForm}{saved && <p role="status" className="mt-3 text-sm font-bold uppercase tracking-[0.08em] text-[var(--tt-blue)]">✓ Tip added</p>}</aside>;
  }

  return <section id="tips" className="tt-section-rule mt-10 scroll-mt-6 pt-4" aria-labelledby="tips-heading"><span id="tips-add" className="block scroll-mt-6" aria-hidden="true"/><p className="tt-kicker">04 / From the terrace</p><div className="mt-1 flex flex-wrap items-end justify-between gap-3"><div><h2 id="tips-heading" className="tt-display text-4xl leading-none sm:text-5xl">Matchday tips</h2><p className="mt-2 text-sm text-[var(--tt-muted)]">Supporter knowledge for a better day at the ground.</p></div>{tipList.length > 0 && <button type="button" onClick={toggleForm} className="tt-action tt-action-secondary px-5">{showForm ? "Cancel" : "Add a tip"}</button>}</div>{tipForm}{!showForm && error && <p role="alert" className="mt-4 border-l-4 border-red-700 px-3 py-2 text-sm font-semibold text-red-800">{error}</p>}{tipList.length === 0 ? <div className="mt-5 border-y-2 border-[var(--tt-ink)] py-6"><p className="tt-display text-3xl">No tips from the terrace yet.</p><p className="mt-2 text-[var(--tt-muted)]">Know this ground? Share one useful thing for the next supporter.</p>{!showForm && <button type="button" onClick={toggleForm} className="mt-3 min-h-11 text-xs font-extrabold uppercase tracking-[0.1em] text-[var(--tt-blue)] underline decoration-2 underline-offset-4">Add a tip →</button>}</div> : <div className="mt-5">{tipList.map((tip) => <article key={tip.tip_id} className="border-t-2 border-[var(--tt-ink)] py-5"><p className="max-w-3xl whitespace-pre-wrap break-words leading-7">{tip.tip}</p><div className="mt-3 flex flex-wrap gap-4 text-xs font-extrabold uppercase tracking-[0.08em]"><button type="button" onClick={() => markHelpful(tip.tip_id)} className="min-h-11 text-[var(--tt-blue)] underline decoration-2 underline-offset-4">Helpful · {tip.helpful_votes}</button></div></article>)}</div>}</section>;
}
