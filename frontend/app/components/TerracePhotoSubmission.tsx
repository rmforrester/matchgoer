"use client";
import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "./AuthProvider";
import TerracePhotoView from "./TerracePhotoView";
import TerracePhotoPreview from "./TerracePhotoPreview";
import { uploadFeedback, refreshFailure, uncertainPhotoResponse, type PhotoFeedback } from "@/lib/terraces-feedback";
import { occupiedPhotoSlots, photoMetadata, terracesError, validatePhotoSelection, type PhotoAttendance, type TerracePhoto } from "@/lib/terraces";

import { reconcilePhotoDrafts, photoStatus, type PhotoDraft as Draft } from "@/lib/terraces-reconciliation";
export default function TerracePhotoSubmission({ attendance }: { attendance: PhotoAttendance }) {
  const { accountKey, authenticated } = useAuth();
  return authenticated ? <PhotoSubmissionContent key={`${accountKey}:${attendance.visit_id}`} attendance={attendance} /> : null;
}

function PhotoSubmissionContent({ attendance }: { attendance: PhotoAttendance }) {
  const { authenticated } = useAuth();
  const [selectedPhoto, setSelectedPhoto] = useState<number | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const detail = useRef<HTMLDialogElement>(null);
  const [photos, setPhotos] = useState<TerracePhoto[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [consent, setConsent] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState<PhotoFeedback | null>(null);
  const error = feedback?.kind === "error" ? feedback.text : "";
  const message = feedback?.kind === "success" ? feedback.text : "";
  const setError = (text: string) => setFeedback(text ? { kind: "error", text } : null);
  const setMessage = (text: string) => setFeedback(text ? { kind: "success", text } : null);
  const request = useRef(0); const writing = useRef(false);
  const scope = useRef(new AbortController());
  useEffect(() => {
    scope.current = new AbortController();
    const controller = scope.current; const requests = request;
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => { window.clearTimeout(timer); controller.abort(); ++requests.current; };
  // This component is keyed by stable account and owned visit identity.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (selectedPhoto !== null) detail.current?.showModal();
    else detail.current?.close();
  }, [selectedPhoto]);
  if (!authenticated) return null;
  async function refresh(clearError = true, confirmed?: PhotoFeedback) {
    if (writing.current) return;
    const generation = ++request.current; setBusy(true); if (clearError) setError("");
    try {
      const response = await api.get<{ photos: TerracePhoto[]; reconciliation_supported?: boolean }>(`/terraces/visits/${attendance.visit_id}/photos`, { signal: scope.current?.signal });
      if (scope.current?.signal.aborted || generation !== request.current) return;
      setPhotos(response.data.photos.filter(photo => photo.status !== "REMOVED")); setLoaded(true);
      if (response.data.reconciliation_supported) setDrafts(current => reconcilePhotoDrafts(current, response.data.photos));
      return response.data.reconciliation_supported ? response.data.photos : undefined;
    } catch (e) { if (!scope.current?.signal.aborted && generation === request.current) {
      setFeedback(confirmed ? refreshFailure(confirmed) : { kind: "error", text: terracesError(e) });
      const status = (e as { response?: { status?: number } })?.response?.status;
      if (status === 401 || status === 403 || status === 404) { setPhotos([]); setLoaded(false); }
    } }
    finally { if (generation === request.current) setBusy(false); }
  }
  async function submit() {
    if (writing.current) return;
    if (!consent || drafts.length === 0) return;
    if (drafts.some(draft => draft.outcome === "uncertain")) {
      await refresh(); return;
    }
    // Retries retain the original file, consent, caption and UUID after an uncertain response.
    const fresh = drafts.filter(draft => !draft.attempted);
    const invalid = fresh.length ? validatePhotoSelection(fresh.map(d => d.file), occupiedPhotoSlots(photos)) : null;
    if (invalid) { setError(invalid); return; }
    writing.current = true; ++request.current; setBusy(true); setSending(true); setError(""); setMessage("");
    let sent = 0; let reviewed = false; let outcome: PhotoFeedback | undefined;
    try {
      for (const draft of drafts) {
        if (scope.current?.signal.aborted) return;
        setDrafts(current => current.map(item => item.key === draft.key ? { ...item, attempted: true, outcome: "uncertain", error: undefined } : item));
        const result = await api.post<{ photo_id: number; status: string }>(`/terraces/visits/${attendance.visit_id}/photos`, draft.file, {
          headers: { "Content-Type": draft.file.type || "application/octet-stream", "Idempotency-Key": draft.key, "X-Terraces-Metadata": photoMetadata(draft.caption, consent) }, timeout: 60_000, signal: scope.current?.signal,
        });
        if (scope.current?.signal.aborted) return;
        if (!["PENDING", "APPROVED"].includes(result.data.status) || !Number.isInteger(result.data.photo_id)) throw new Error("Submission not confirmed");
        setPhotos(current => current.some(photo => photo.photo_id === result.data.photo_id) ? current : [...current, {
          photo_id: result.data.photo_id, venue_id: attendance.venue_id, fixture_id: attendance.fixture_id,
          caption: draft.caption || null, display_name: "", published_at: null, match_date: attendance.match_date,
          home_team: attendance.home_team, away_team: attendance.away_team,
          status: result.data.status as "PENDING" | "APPROVED",
        }]);
        sent++; reviewed ||= result.data.status === "APPROVED";
        setDrafts(current => current.filter(item => item.key !== draft.key));
      }
      outcome = uploadFeedback(sent, drafts.length, "", reviewed); setFeedback(outcome);
    } catch (e) {
      if (scope.current?.signal.aborted) return;
      setDrafts(current => current.map(item => item.attempted ? { ...item, outcome: uncertainPhotoResponse(e) ? "uncertain" : "failed", error: terracesError(e) } : item));
      outcome = uploadFeedback(sent, drafts.length, terracesError(e), false, uncertainPhotoResponse(e)); setFeedback(outcome);
    }
    finally { writing.current = false; if (!scope.current?.signal.aborted) { setSending(false); setBusy(false); const latest = await refresh(false, sent > 0 ? outcome : undefined);
      if (latest) {
        const remaining = reconcilePhotoDrafts(drafts.map(d => ({ ...d, attempted: true })), latest);
        const confirmedCount = drafts.filter(d => latest.some(p => p.submission_key === d.key && p.upload_state === "ready")).length;
        if (!remaining.length) setMessage(drafts.some(d => latest.some(p => p.submission_key === d.key && p.status !== "PENDING")) ? "Your photos are saved." : drafts.length === 1 ? "Photo sent. Pending review." : "Photos sent. Pending review.");
        else if (confirmedCount > sent) setFeedback(uploadFeedback(confirmedCount, drafts.length, "Couldn't send that photo. Try again."));
      } } }
  }
  async function remove(photo: TerracePhoto) {
    if (writing.current) return; writing.current = true; ++request.current; setBusy(true); setError(""); setMessage("");
    try {
      const response = await api.delete(`/terraces/photos/${photo.photo_id}`, { signal: scope.current?.signal });
      if (scope.current?.signal.aborted) return;
      if (response.data.status !== "REMOVED" || response.data.photo_id !== photo.photo_id) throw new Error("Removal not confirmed");
      setPhotos(current => current.filter(item => item.photo_id !== photo.photo_id));
      setSelectedPhoto(null);
      setMessage("Photo removed.");
    } catch (e) { if (!scope.current?.signal.aborted) setError(terracesError(e)); }
    finally { writing.current = false; setBusy(false); }
  }
  const occupied = occupiedPhotoSlots(photos);
  const ordered = [...photos].sort((a, b) => Number(a.status === "REJECTED") - Number(b.status === "REJECTED"));
  const visible = ordered.slice(0, occupied < 3 ? 2 : 3);
  const enlarged = photos.find(photo => photo.photo_id === selectedPhoto);
  const uncertain = drafts.some(draft => draft.outcome === "uncertain");
  function choose(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    const invalid = validatePhotoSelection([...drafts.map(draft => draft.file), ...files], occupied);
    setError(invalid ?? "");
    if (!invalid) { setDrafts(current => [...current, ...files.map(file => ({ file, caption: "", key: crypto.randomUUID(), attempted: false }))]); setConsent(false); }
    event.target.value = "";
  }
  return <section aria-label={`Photos from ${attendance.venue_name}`} className="mt-3 min-w-0 border-t border-[var(--tt-rule)] pt-3">
    <div className="flex items-center justify-between gap-2"><h3 className="tt-display text-2xl uppercase">From the Terraces</h3><span className="shrink-0 text-xs text-[var(--tt-muted)]">{occupied}/3 photos</span></div>
    {busy && <p role="status" className="text-sm">{sending ? drafts.length === 1 ? "Sending your photo\u2026" : "Sending your photos\u2026" : "One moment\u2026"}</p>}
    {error && <p role="alert" className="mt-2 text-sm font-bold text-red-800">{error}</p>}
    {message && <p role="status" className="mt-2 text-sm font-bold">{message}</p>}
    {!loaded && !busy && <button type="button" onClick={() => void refresh()} className="min-h-11 text-sm underline">Try again</button>}
    {loaded && <>
      <input ref={picker} aria-label="Choose photographs" type="file" multiple accept="image/jpeg,image/png,image/heic,image/heif,.heic,.heif" disabled={busy} tabIndex={-1} className="sr-only" onChange={choose} />
      {!drafts.length && <div className="mt-3 grid grid-cols-3 items-start gap-2">
        {visible.map(photo => <article key={photo.photo_id} className="relative min-w-0">
          <TerracePhotoView photo={photo} refresh={() => void refresh()} showContext={false} compact onOpen={() => setSelectedPhoto(photo.photo_id)} />
          <span className={photo.status === "APPROVED" ? "sr-only" : `pointer-events-none absolute bottom-0 left-0 px-2 py-1 text-[0.65rem] font-bold uppercase ${photo.status === "PENDING" ? "bg-[var(--tt-gold)] text-black" : photo.status === "REJECTED" ? "bg-[var(--tt-paper)] text-black" : "bg-[var(--brand-interactive)] text-white"}`}>{photoStatus(photo)}</span>
        </article>)}
        {occupied < 3 && <button type="button" disabled={busy} aria-label="Add photos" onClick={() => picker.current?.click()} className="flex aspect-square min-h-11 flex-col items-center justify-center border border-dashed border-[var(--tt-rule)] px-1 text-xs font-bold uppercase"><span aria-hidden="true" className="text-3xl font-normal">+</span>Add photo</button>}
        {Array.from({ length: Math.max(0, 3 - visible.length - (occupied < 3 ? 1 : 0)) }, (_, i) => <div key={i} aria-hidden="true" className="aspect-square border border-dashed border-[var(--tt-rule)]" />)}
      </div>}
      <dialog ref={detail} onClose={() => setSelectedPhoto(null)} className="m-auto max-h-[90dvh] w-[calc(100%-2rem)] max-w-xl overflow-auto bg-[var(--tt-paper)] p-4 text-[var(--tt-ink)] backdrop:bg-black/60" aria-label="Matchday photo details">
        <button type="button" onClick={() => setSelectedPhoto(null)} className="mb-2 min-h-11 font-bold underline">Close photo</button>
        {enlarged && <><TerracePhotoView photo={enlarged} refresh={() => void refresh()} showContext={false} /><p className="mt-2 text-sm font-bold">{photoStatus(enlarged)}</p><button type="button" disabled={busy} onClick={() => void remove(enlarged)} className="mt-2 min-h-11 text-sm font-bold underline">REMOVE PHOTO</button></>}
      </dialog>
      {drafts.length > 0 && <div className="mt-4 min-w-0">
        <h4 className="tt-display text-3xl">ADD PHOTOS</h4><p className="mt-1 text-sm">Share your matchday.</p>
        <div className="mt-3 grid grid-cols-2 items-start gap-3">
          {drafts.map((draft, index) => <div key={draft.key} className="relative min-w-0">
            <TerracePhotoPreview file={draft.file} />
            <button type="button" disabled={busy || draft.outcome === "uncertain"} aria-label={`Remove selected photo ${index + 1}`} onClick={() => { setDrafts(current => current.filter(item => item.key !== draft.key)); setFeedback(null); }} className="absolute right-0 top-0 flex h-11 w-11 items-center justify-center bg-[var(--tt-paper)] text-2xl">×</button>
            <label className="mt-2 grid min-w-0 gap-1 text-xs"><span>Caption {index + 1} (optional)</span><textarea value={draft.caption} disabled={busy || draft.attempted} maxLength={200} rows={2} className="tt-control w-full min-w-0 p-2 text-sm" onChange={event => setDrafts(current => current.map(item => item.key === draft.key ? { ...item, caption: event.target.value } : item))} /><span>{draft.caption.length}/200</span></label>
            {draft.error && <p className="mt-1 text-xs text-red-800">{draft.error}</p>}
          </div>)}
        </div>
        {drafts.length + occupied < 3 && !drafts.some(d => d.attempted) && <button type="button" disabled={busy} onClick={() => picker.current?.click()} className="mt-3 min-h-11 w-full border border-dashed border-[var(--tt-rule)] text-sm">+ Add another photo</button>}
        <p className="mt-2 text-xs text-[var(--tt-muted)]">JPEG, PNG &amp; iPhone photos · Max 10 MB each.</p>
        <label className="mt-5 flex items-start gap-2 text-sm"><input type="checkbox" checked={consent} disabled={busy || drafts.some(d => d.attempted)} onChange={event => setConsent(event.target.checked)} className="mt-1 h-5 w-5 shrink-0" /><span>I have permission to share these photos publicly on Matchgoer.</span></label>
        <p className="mt-1 text-xs text-[var(--tt-muted)]">Shared with your display name after review.</p>
        <button type="button" disabled={busy || !consent} onClick={() => void submit()} className="tt-action mt-4 w-full px-3">{busy ? "Sending…" : uncertain ? "CHECK PHOTOS" : drafts.some(d => d.attempted) ? "TRY AGAIN" : "SHARE PHOTOS →"}</button>
        {!uncertain && <button type="button" disabled={busy} onClick={() => { setDrafts([]); setConsent(false); setFeedback(null); }} className="min-h-11 text-sm font-bold underline">Cancel selection</button>}
      </div>}
    </>}
  </section>;
}
