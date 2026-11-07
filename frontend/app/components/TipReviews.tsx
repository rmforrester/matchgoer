"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import api from "../../lib/api";
import { apiErrorMessage } from "../../lib/api-error";
import { MODERATION_CHANGED } from "./ModeratorAttentionDot";

type Status = "PENDING" | "APPROVED" | "REJECTED";
type Tip = { tip_id: number; venue_id: number | null; venue_name: string; venue_city: string | null; venue_country: string | null; tip: string; category: string | null; created_at: string | null; status: Status };
export default function TipReviews() {
  const [state, setState] = useState<Status>("PENDING");
  const [tips, setTips] = useState<Tip[]>([]);
  const [count, setCount] = useState(0);
  const [next, setNext] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const request = useRef(0);
  const writing = useRef(false);
  const scope = useRef<AbortController | null>(null);
  const load = useCallback(async (status: Status, after = 0) => {
    const version = ++request.current; setBusy(true); setError("");
    try {
      const { data } = await api.get<{ tips: Tip[]; pending_count: number; next_id: number | null }>("/moderator/tips", { params: { state: status, after_id: after }, signal: scope.current?.signal });
      if (version !== request.current || scope.current?.signal.aborted) return;
      setTips(current => after ? [...new Map([...current, ...data.tips].map(tip => [tip.tip_id, tip])).values()] : data.tips);
      setCount(data.pending_count); setNext(data.next_id);
    } catch (e) { if (version === request.current && !scope.current?.signal.aborted) { setTips([]); setError(apiErrorMessage(e, "Unable to load tip reviews. Administrator access is required.")); } }
    finally { if (version === request.current && !scope.current?.signal.aborted) setBusy(false); }
  }, []);
  useEffect(() => {
    const controller = new AbortController(); scope.current = controller; const generation = request;
    const timer = window.setTimeout(() => void load("PENDING"), 0);
    return () => { window.clearTimeout(timer); controller.abort(); generation.current++; };
  }, [load]);
  async function moderate(tip: Tip, decision: "APPROVE" | "REJECT") {
    if (writing.current) return;
    writing.current = true; request.current++; setBusy(true); setError(""); setMessage("");
    try {
      const { data } = await api.post(`/moderator/tips/${tip.tip_id}`, { decision, expected_status: tip.status }, { signal: scope.current?.signal });
      if (scope.current?.signal.aborted) return;
      const expected = decision === "APPROVE" ? "APPROVED" : "REJECTED";
      if (data.tip_id !== tip.tip_id || data.status !== expected) throw new Error("Decision was not confirmed");
      setMessage(decision === "APPROVE" ? "Tip approved. It is now available on this ground's Community Tips." : "Tip rejected. It is not publicly visible.");
      setTips(current => current.filter(item => item.tip_id !== tip.tip_id));
      window.dispatchEvent(new Event(MODERATION_CHANGED));
      await load(state);
    } catch (e) { if (!scope.current?.signal.aborted) setError(apiErrorMessage(e, "The decision could not be confirmed. Refresh before trying again.")); }
    finally { writing.current = false; if (!scope.current?.signal.aborted) setBusy(false); }
  }
  return <section className="mt-4" aria-label="Tip Reviews">
    <nav aria-label="Tip review status" className="grid grid-cols-3 border-b border-[var(--tt-rule)]">
      {(["PENDING", "APPROVED", "REJECTED"] as const).map(status => <button type="button" key={status} disabled={busy} aria-current={state === status ? "page" : undefined} className={`min-h-11 text-xs font-extrabold ${state === status ? "underline decoration-2 underline-offset-4" : ""}`} onClick={() => { setState(status); setTips([]); setMessage(""); void load(status); }}>{status}{status === "PENDING" ? ` (${count})` : ""}</button>)}
    </nav>
    {busy && <p role="status" className="mt-3">Loading tip reviews…</p>}
    {message && <p role="status" className="mt-3 font-bold">{message}</p>}
    {error && <p role="alert" className="mt-3 text-sm font-bold text-red-800">{error}</p>}
    {!busy && !error && !tips.length && <p className="py-4">No {state.toLowerCase()} tips.</p>}
    {tips.map(tip => <article key={tip.tip_id} className="min-w-0 border-b border-[var(--tt-rule)] py-4">
      <h2 className="tt-display break-words text-2xl">{tip.venue_name}</h2><p className="text-sm">{[tip.venue_city, tip.venue_country].filter(Boolean).join(" · ")}</p>
      <p className="mt-1 text-xs">Submitted: {tip.created_at?.slice(0, 10) || "Not recorded"} · {tip.status}</p>
      {tip.category && <p className="mt-2 text-xs font-bold">{tip.category}</p>}
      <p className="my-3 whitespace-pre-wrap break-words text-sm leading-relaxed">{tip.tip}</p>
      <div className="grid grid-cols-2 gap-2">
        <button type="button" disabled={busy || tip.status === "APPROVED"} onClick={() => void moderate(tip, "APPROVE")} className="tt-action min-h-11 px-2 text-xs">Approve</button>
        <button type="button" disabled={busy || tip.status === "REJECTED"} onClick={() => void moderate(tip, "REJECT")} className="tt-action tt-action-danger min-h-11 px-2 text-xs">Reject</button>
      </div>
    </article>)}
    {next !== null && <button type="button" disabled={busy} onClick={() => void load(state, next)} className="min-h-11 font-bold underline">Load more tips</button>}
    <button type="button" disabled={busy} onClick={() => void load(state)} className="mt-3 min-h-11 font-bold underline">Refresh tip reviews</button>
  </section>;
}
