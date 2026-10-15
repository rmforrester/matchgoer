"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "./AuthProvider";
import TerracePhotoView from "./TerracePhotoView";
import { terracesError, type PhotoReport, type TerracePhoto } from "@/lib/terraces";
import type { PhotoFeedback } from "@/lib/terraces-feedback";

type State = "PENDING" | "APPROVED" | "REPORTS";
type ModeratorPage = { photos: TerracePhoto[]; pending_count: number; next_id: number | null };
export function ManageSubmissionsLink() {
  const { authenticated, accountKey } = useAuth();
  const [allowedFor, setAllowedFor] = useState<string | null>(null);
  useEffect(() => {
    if (!authenticated) return;
    const controller = new AbortController();
    // This existing protected read is the capability check; no frontend ID list.
    void api.get<ModeratorPage>("/terraces/moderator/photos", { params: { limit: 1 }, signal: controller.signal })
      .then(() => { if (!controller.signal.aborted) setAllowedFor(accountKey); }).catch(() => { if (!controller.signal.aborted) setAllowedFor(null); });
    return () => controller.abort();
  }, [authenticated, accountKey]);
  return authenticated && allowedFor === accountKey ? <Link href="/account/submissions" className="block min-h-11 content-center font-bold underline underline-offset-4">Manage Submissions</Link> : null;
}

export default function TerraceModeration() {
  const { accountKey } = useAuth();
  return <TerraceModerationContent key={accountKey} />;
}

function TerraceModerationContent() {
  const { authenticated, loading } = useAuth();
  const [allowed, setAllowed] = useState(false);
  const [tab, setTab] = useState<State>("PENDING");
  const [photos, setPhotos] = useState<TerracePhoto[]>([]);
  const [reports, setReports] = useState<PhotoReport[]>([]);
  const [count, setCount] = useState(0);
  const [next, setNext] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<PhotoFeedback | null>(null);
  const error = feedback?.kind === "error" ? feedback.text : "";
  const message = feedback?.kind === "success" ? feedback.text : "";
  const setError = useCallback((text: string) => setFeedback(text ? { kind: "error", text } : null), []);
  const setMessage = (text: string) => setFeedback(text ? { kind: "success", text } : null);
  const [rejecting, setRejecting] = useState<number | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const scope = useRef(new AbortController());
  const removedFromQueue = useRef(new Set<string>());
  const resolved = useRef(new Set<number>());
  useEffect(() => {
    if (feedback?.kind !== "success") return;
    const timer = window.setTimeout(() => setFeedback(null), 4000);
    return () => window.clearTimeout(timer);
  }, [feedback]);
  const generation = useRef(0); const writing = useRef(false); const selectedTab = useRef(tab);
  const load = useCallback(async (state: State, after = 0, clear = true, confirmed?: string) => {
    if (writing.current) return;
    const request = ++generation.current; setBusy(true); if (clear) setError("");
    try {
      // Every tab is independently protected by B1, including Reported.
      if (state === "REPORTS") {
        const response = await api.get<{ reports: PhotoReport[]; next_id: number | null }>("/terraces/moderator/reports", { params: { after_id: after } });
        const pending = await api.get<ModeratorPage>("/terraces/moderator/photos", { params: { limit: 1 } });
        const detail = await Promise.all(response.data.reports.map(report => report.photo_id === null ? null : api.get<TerracePhoto>(`/terraces/photos/${report.photo_id}`).then(result => result.data).catch(() => null)));
        if (scope.current?.signal.aborted || request !== generation.current || selectedTab.current !== state) return;
        setReports(current => Array.from(new Map((after ? [...current, ...response.data.reports] : response.data.reports).filter(report => !resolved.current.has(report.report_id)).map(report => [report.report_id, report])).values()));
        setPhotos(current => Array.from(new Map((after ? [...current, ...detail.filter((photo): photo is TerracePhoto => photo !== null)] : detail.filter((photo): photo is TerracePhoto => photo !== null)).map(photo => [photo.photo_id, photo])).values()));
        setCount(pending.data.pending_count); setNext(response.data.next_id);
      } else {
        const response = await api.get<ModeratorPage>("/terraces/moderator/photos", { params: { state, after_id: after } });
        if (scope.current?.signal.aborted || request !== generation.current || selectedTab.current !== state) return;
        const eligible = response.data.photos.filter(photo => photo.status === state && photo.upload_state === "ready" && (state !== "APPROVED" || photo.published_at) && !removedFromQueue.current.has(`${state}:${photo.photo_id}`));
        setPhotos(current => Array.from(new Map((after ? [...current, ...eligible] : eligible).map(photo => [photo.photo_id, photo])).values())); setReports([]);
        setCount(Math.max(0, response.data.pending_count - (state === "PENDING" ? response.data.photos.filter(photo => removedFromQueue.current.has(`PENDING:${photo.photo_id}`)).length : 0))); setNext(response.data.next_id);
      }
      setAllowed(true);
    } catch (e) {
      if (!scope.current?.signal.aborted && request === generation.current) {
        setError(confirmed ? `${confirmed} Can't load the latest photos right now.` : terracesError(e));
        const status = (e as { response?: { status?: number } }).response?.status;
        if (status === 401 || status === 403 || status === 404) { setAllowed(false); setPhotos([]); setReports([]); }
      }
    } finally { if (!scope.current?.signal.aborted && request === generation.current) setBusy(false); }
  }, [setError]);
  useEffect(() => {
    if (!authenticated) return;
    scope.current = new AbortController();
    const requests = generation;
    const timer = window.setTimeout(() => void load("PENDING"), 0);
    return () => { window.clearTimeout(timer); scope.current?.abort(); ++requests.current; };
  }, [authenticated, load]);
  async function action(path: string, method: "post" | "delete", expected: string, noteKey?: string) {
    if (writing.current) return;
    const reason = noteKey ? notes[noteKey]?.trim() : undefined;
    if (noteKey && !reason) { setError("Add a short reason first."); return; }
    writing.current = true; ++generation.current; setBusy(true); setError(""); setMessage("");
    let confirmed: string | undefined;
    try {
      const response = method === "delete" ? await api.delete(path, { signal: scope.current?.signal }) : await api.post(path, reason ? { reason } : undefined, { signal: scope.current?.signal });
      if (scope.current?.signal.aborted) return;
      if (response.data.status !== expected) throw new Error("Action not confirmed");
      if (expected === "resolved") { resolved.current.add(response.data.report_id); setReports(current => current.filter(report => report.report_id !== response.data.report_id)); }
      else {
        removedFromQueue.current.add(`${tab}:${response.data.photo_id}`);
        setPhotos(current => current.filter(photo => photo.photo_id !== response.data.photo_id));
        if (tab === "PENDING") setCount(current => Math.max(0, current - 1));
      }
      confirmed = expected === "APPROVED" ? "Photo is live." : expected === "REJECTED" ? "Photo won't be shared." : expected === "resolved" ? "Report resolved." : "Photo removed.";
      setMessage(confirmed); setRejecting(null); setNotes({});
    } catch (e) { if (!scope.current?.signal.aborted) setError(terracesError(e)); }
    finally { writing.current = false; if (!scope.current?.signal.aborted) { setBusy(false); await load(tab, 0, false, confirmed); } }
  }
  function reason(key: string, label: string) {
    return <label className="mt-3 grid gap-1 text-sm font-bold">{label}<textarea maxLength={200} rows={2} disabled={busy} className="tt-control w-full min-w-0 p-2 font-normal" value={notes[key] ?? ""} onChange={event => setNotes(current => ({ ...current, [key]: event.target.value }))} /><span className="font-normal">{(notes[key] ?? "").length}/200</span></label>;
  }
  if (loading) return <p role="status">Checking your account…</p>;
  if (!authenticated) return <p className="mt-4">Sign in to manage submissions.</p>;
  return <div className="mt-5 min-w-0">
    {busy && <p role="status">One moment…</p>}{error && <p role="alert" className="mb-3 text-sm font-bold text-red-800">{error}</p>}{message && <p role="status" className="mb-3 font-bold">{message}</p>}
    {!allowed ? <button disabled={busy} onClick={() => void load("PENDING")} className="min-h-11 font-bold underline">Try again</button> : <>
      <nav aria-label="Submission sections" className="my-3 grid grid-cols-3 gap-1 border-b border-[var(--tt-rule)]">
        {([['PENDING', 'Pending'], ['APPROVED', 'Published'], ['REPORTS', 'Reported']] as const).map(([state, label]) => <button type="button" key={state} disabled={busy} aria-current={tab === state ? "page" : undefined} className={`min-h-11 min-w-0 text-xs font-extrabold uppercase ${tab === state ? "underline decoration-2 underline-offset-4" : ""}`} onClick={() => { selectedTab.current = state; setTab(state); setPhotos([]); setReports([]); setMessage(""); void load(state); }}>{label}{state === "PENDING" ? ` (${count})` : ""}</button>)}
      </nav>
      {tab !== "REPORTS" && !photos.length && !busy && !error && <p className="py-4">{tab === "PENDING" ? "All caught up." : "Nothing here yet."}</p>}
      {tab !== "REPORTS" && photos.map(photo => <article key={photo.photo_id} className="min-w-0 border-b border-[var(--tt-rule)] py-3">
        <TerracePhotoView photo={photo} refresh={() => void load(tab)} showContext={false} showCaption={false} />
        <p className="mt-2 break-words font-bold">{photo.venue_name || "Ground not recorded"}</p>
        <p className="mt-1 text-sm font-bold">{photo.home_team && photo.away_team ? `${photo.home_team} v ${photo.away_team}` : "Historical matchday"}</p>
        <p className="text-xs text-[var(--tt-muted)]">Match date: {photo.match_date?.slice(0, 10) || "Not recorded"} &middot; Submitted: {photo.submitted_at?.slice(0, 10) || "Not recorded"}</p>
        {photo.display_name && <p className="mt-1 break-words text-xs text-[var(--tt-muted)]">{photo.display_name}</p>}{photo.caption && <p className="mt-1 break-words text-sm">{photo.caption}</p>}
        {photo.held && <p className="text-sm font-bold">Keep this photo while the concern is reviewed.</p>}
        {tab === "PENDING" ? <>
          <div className="clear-both mt-3 grid grid-cols-2 gap-2">
            <button disabled={busy} onClick={() => void action(`/terraces/moderator/photos/${photo.photo_id}/approve`, "post", "APPROVED")} className="tt-action px-2 text-xs">APPROVE &amp; SHARE</button>
            <button disabled={busy} aria-expanded={rejecting === photo.photo_id} onClick={() => setRejecting(current => current === photo.photo_id ? null : photo.photo_id)} className="tt-action tt-action-secondary px-2 text-xs">{rejecting === photo.photo_id ? "CANCEL REJECTION" : "DO NOT SHARE"}</button>
          </div>
          {rejecting === photo.photo_id && <>{reason(`photo-${photo.photo_id}`, "Reason for rejection")}
            <button disabled={busy || !notes[`photo-${photo.photo_id}`]?.trim()} onClick={() => void action(`/terraces/moderator/photos/${photo.photo_id}/reject`, "post", "REJECTED", `photo-${photo.photo_id}`)} className="min-h-11 text-sm font-bold underline">CONFIRM REJECTION</button></>}
        </> : <button disabled={busy} onClick={() => void action(`/terraces/moderator/photos/${photo.photo_id}`, "delete", "REMOVED")} className="min-h-11 font-bold underline">REMOVE PHOTO</button>}
      </article>)}
      {tab === "REPORTS" && !reports.length && !busy && !error && <p className="py-4">Nothing here yet.</p>}
      {tab === "REPORTS" && reports.map(report => { const photo = photos.find(item => item.photo_id === report.photo_id); return <article key={report.report_id} className="min-w-0 border-b border-[var(--tt-rule)] py-3">
        {photo ? <><TerracePhotoView photo={photo} refresh={() => void load(tab)} showContext={false} showCaption={false} /><p className="mt-2 break-words font-bold">{photo.venue_name || "Ground not recorded"}</p>
        <p className="mt-1 text-sm font-bold">{photo.home_team && photo.away_team ? `${photo.home_team} v ${photo.away_team}` : "Historical matchday"}</p>
        <p className="text-xs text-[var(--tt-muted)]">Match date: {photo.match_date?.slice(0, 10) || "Not recorded"} &middot; Submitted: {photo.submitted_at?.slice(0, 10) || "Not recorded"}</p>
        {photo.display_name && <p className="mt-1 break-words text-xs text-[var(--tt-muted)]">{photo.display_name}</p>}{photo.caption && <p className="mt-1 break-words text-sm">{photo.caption}</p>}</> : <p>Can&apos;t show this reported photo right now.</p>}
        <p className="mt-2 break-words text-sm"><strong>Report:</strong> {report.reason}</p>
        {photo?.status === "APPROVED" && <button disabled={busy} onClick={() => void action(`/terraces/moderator/photos/${photo.photo_id}`, "delete", "REMOVED")} className="min-h-11 font-bold underline">REMOVE PHOTO</button>}
        {reason(`report-${report.report_id}`, "Resolution note")}
        <button disabled={busy || !notes[`report-${report.report_id}`]?.trim()} onClick={() => void action(`/terraces/moderator/reports/${report.report_id}/resolve`, "post", "resolved", `report-${report.report_id}`)} className="tt-action mt-2 w-full px-3">RESOLVE REPORT</button>
      </article>; })}
      {next !== null && <button disabled={busy} onClick={() => void load(tab, next)} className="min-h-11 font-bold underline">Load more</button>}
      <button disabled={busy} onClick={() => void load(tab)} className="mt-3 block min-h-11 font-bold underline">Refresh submissions</button>
    </>}
  </div>;
}
