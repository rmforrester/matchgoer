"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthProvider";
import { MODERATION_CHANGED } from "./ModeratorAttentionDot";
import api from "../../lib/api";
import { apiErrorMessage } from "../../lib/api-error";

type Tip = { tip_id: number; can_block_author?: boolean; venue_id: number; tip: string; helpful_votes: number; report_count: number; status: string; created_at: string };
const EMPTY_TIPS: Tip[] = [];

type Props = { tips?: Tip[]; venueId: number; inline?: boolean };

export default function MatchdayTips(props: Props) {
  const { accountKey } = useAuth();
  return <MatchdayTipsContent key={`${accountKey}:${props.venueId}`} {...props} />;
}

function MatchdayTipsContent({ tips = EMPTY_TIPS, venueId, inline = false }: Props) {
  const { authenticated, accountKey } = useAuth();
  const safetyScope = useRef<AbortController | null>(null);
  useEffect(() => { const controller = new AbortController(); safetyScope.current = controller; return () => controller.abort(); }, [accountKey]);
  const [safetyMessage, setSafetyMessage] = useState("");
  const [tipList, setTipList] = useState<Tip[]>(tips);
  const [showForm, setShowForm] = useState(false);
  const [newTip, setNewTip] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const writing = useRef(false);
  const [receipt, setReceipt] = useState("Tip sent for review");
  const [tipScope, setTipScope] = useState(`${accountKey}:${venueId}`);
  const visibleTips = tipScope === `${accountKey}:${venueId}` ? tipList.filter(tip => tip.venue_id === venueId && (tip.status === "active" || tip.status === "APPROVED")) : [];
  useEffect(() => {
    const controller = new AbortController(); let version = 0;

    const refresh = async () => {
      const current = ++version;
      try {
        const { data } = await api.get<Tip[]>(`/venues/${venueId}/tips`, { signal: controller.signal });
        if (!Array.isArray(data)) throw new Error("Invalid public tip response");
        if (!controller.signal.aborted && current === version) { setTipScope(`${accountKey}:${venueId}`); setTipList(data); }
      } catch { if (!controller.signal.aborted && current === version) setTipList([]); }
    };
    void refresh();
    const invalidate = () => { setTipList([]); void refresh(); };
    window.addEventListener("focus", refresh); window.addEventListener(MODERATION_CHANGED, invalidate);
    const visible = () => { if (document.visibilityState === "visible") void refresh(); };
    document.addEventListener("visibilitychange", visible);
    return () => { controller.abort(); window.removeEventListener("focus", refresh); window.removeEventListener(MODERATION_CHANGED, invalidate); document.removeEventListener("visibilitychange", visible); };
  }, [venueId, accountKey]);

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
    try { const response = await api.post(`/tips/${tipId}/helpful`); setTipList((current) => current.map((tip) => tip.tip_id === tipId ? { ...tip, ...response.data, venue_id: tip.venue_id, can_block_author: tip.can_block_author } : tip)); }
    catch (requestError) { setError(apiErrorMessage(requestError, "Could not mark that tip as helpful.")); }
  };
  const reportTip = async (tipId: number) => {
    try { await api.post(`/tips/${tipId}/report`, undefined, { signal: safetyScope.current?.signal }); setSafetyMessage("Tip reported for review."); }
    catch { setError("Couldn't report this tip. Please try again."); }
  };
  const blockTip = async (tipId: number) => {
    try {
      await api.post(`/tips/${tipId}/block-author`, undefined, { signal: safetyScope.current?.signal });
      const response = await api.get(`/venues/${venueId}/tips`, { signal: safetyScope.current?.signal });
      setTipList(response.data); setSafetyMessage("Matchgoer blocked.");
    } catch { setError("Couldn't block this matchgoer. Please try again."); }
  };
  const submitTip = async () => {
    const trimmed = newTip.trim();
    if (!trimmed) { setError("Please enter a tip before submitting."); return; }
    if (writing.current) return;
    writing.current = true;
    setSubmitting(true); setError(""); setSaved(false);
    try {
      const { data } = await api.post("/tips", { venue_id: venueId, tip: trimmed }, { signal: safetyScope.current?.signal });
      if (safetyScope.current?.signal.aborted) return;
      if (!Number.isSafeInteger(data.tip_id) || data.tip_id < 1 || data.venue_id !== venueId || data.tip !== trimmed || !["pending", "reported", "active"].includes(data.status)) throw new Error("Tip persistence not confirmed");
      setReceipt(data.status === "active" ? "This tip is already published" : "Tip sent for review");
      window.dispatchEvent(new Event(MODERATION_CHANGED));
      setNewTip(""); setShowForm(false); setSaved(true);
    } catch (requestError) { setError(apiErrorMessage(requestError, "Could not submit your tip. Please try again.")); }
    finally { writing.current = false; setSubmitting(false); }
  };

  const tipForm = showForm && <div className={`${inline ? "mt-3" : "tt-panel mt-5"} p-4`}><label htmlFor={`venue-tip-${venueId}-${inline ? "inline" : "section"}`} className="tt-kicker">Your matchday advice</label><textarea id={`venue-tip-${venueId}-${inline ? "inline" : "section"}`} maxLength={2000} value={newTip} onChange={(event) => setNewTip(event.target.value)} placeholder="Share useful advice for other supporters…" rows={4} className="tt-control mt-2 w-full resize-y p-3"/><div className="mt-3 flex flex-wrap gap-3"><button type="button" onClick={toggleForm} className="tt-action tt-action-secondary px-4">Cancel</button><button type="button" onClick={submitTip} disabled={submitting || !newTip.trim()} className="tt-action px-5">{submitting ? "Submitting…" : "Submit tip"}</button></div>{error && <p role="alert" className="mt-2 text-sm font-semibold text-red-800">{error}</p>}</div>;

  if (inline) {
    return <aside className="mt-6 border-y-2 border-[var(--tt-ink)] py-4"><p className="tt-display text-2xl">Know something another supporter should know?</p><p className="mt-1 text-sm text-[var(--tt-muted)]">Share useful matchday knowledge for community tip review.</p>{!showForm && <button type="button" onClick={toggleForm} className="mt-2 min-h-11 text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)] underline decoration-2 underline-offset-4">Add a tip →</button>}{tipForm}{saved && <p role="status" className="mt-3 text-sm font-bold uppercase tracking-[0.08em] text-[var(--brand-interactive)]">✓ {receipt}</p>}</aside>;
  }

  if (visibleTips.length === 0) return <section id="tips" className="mt-6 scroll-mt-6" aria-labelledby="tips-heading"><span id="tips-add" className="block scroll-mt-6" aria-hidden="true"/><h2 id="tips-heading" className="sr-only">Community Tips</h2><p className="text-sm font-bold">Know something another supporter should know? <button type="button" onClick={toggleForm} className="min-h-11 text-[var(--brand-interactive)] underline decoration-2 underline-offset-4">Share it for review →</button></p>{tipForm}{saved && <p role="status" className="mt-3 text-sm font-bold uppercase tracking-[0.08em] text-[var(--brand-interactive)]">✓ {receipt}</p>}{!showForm && error && <p role="alert" className="mt-2 text-sm font-semibold text-red-800">{error}</p>}</section>;

  return <section id="tips" className="tt-section-rule mt-10 scroll-mt-6 pt-4" aria-labelledby="tips-heading"><span id="tips-add" className="block scroll-mt-6" aria-hidden="true"/><p className="tt-kicker">04 / From the terrace</p><div className="mt-1 flex flex-wrap items-end justify-between gap-3"><div><h2 id="tips-heading" className="tt-display text-4xl leading-none sm:text-5xl">Community Tips</h2><p className="mt-2 text-sm text-[var(--tt-muted)]">Useful advice from people who&apos;ve been.</p></div><button type="button" onClick={toggleForm} className="tt-action tt-action-secondary px-5">{showForm ? "Cancel" : "Add a tip"}</button></div>{tipForm}{!showForm && error && <p role="alert" className="mt-4 border-l-4 border-red-700 px-3 py-2 text-sm font-semibold text-red-800">{error}</p>}{safetyMessage && <p role="status">{safetyMessage}</p>}<div className="mt-5">{visibleTips.map((tip) => <article key={tip.tip_id} className="border-t-2 border-[var(--tt-ink)] py-5"><p className="max-w-3xl whitespace-pre-wrap break-words leading-7">{tip.tip}</p><div className="mt-3 flex flex-wrap gap-4 text-xs font-extrabold uppercase tracking-[0.08em]"><button type="button" onClick={() => markHelpful(tip.tip_id)} className="min-h-11 text-[var(--brand-interactive)] underline decoration-2 underline-offset-4">Helpful{tip.helpful_votes > 0 ? ` · ${tip.helpful_votes}` : ""}</button><button type="button" onClick={() => void reportTip(tip.tip_id)} className="min-h-11 underline">Report tip</button>{authenticated && tip.can_block_author && <button type="button" onClick={() => void blockTip(tip.tip_id)} className="min-h-11 underline">Block matchgoer</button>}</div></article>)}</div></section>;
}
