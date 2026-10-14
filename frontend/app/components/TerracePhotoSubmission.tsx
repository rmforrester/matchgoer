"use client";
import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "./AuthProvider";
import TerracePhotoView from "./TerracePhotoView";
import TerracePhotoPreview from "./TerracePhotoPreview";
import { uploadFeedback, refreshFailure, uncertainPhotoResponse, type PhotoFeedback } from "@/lib/terraces-feedback";
import { occupiedPhotoSlots, photoMetadata, terracesError, validatePhotoSelection, type PhotoAttendance, type TerracePhoto } from "@/lib/terraces";

type Draft = { file: File; caption: string; key: string; attempted: boolean };
export default function TerracePhotoSubmission({ attendance }: { attendance: PhotoAttendance }) {
  const { accountKey, authenticated } = useAuth();
  return authenticated ? <PhotoSubmissionContent key={`${accountKey}:${attendance.visit_id}`} attendance={attendance} /> : null;
}

function PhotoSubmissionContent({ attendance }: { attendance: PhotoAttendance }) {
  const { authenticated } = useAuth();
  const [selectedPhoto, setSelectedPhoto] = useState<number | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const [photos, setPhotos] = useState<TerracePhoto[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [consent, setConsent] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
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
  if (!authenticated) return null;
  async function refresh(clearError = true, confirmed?: PhotoFeedback) {
    const generation = ++request.current; setBusy(true); if (clearError) setError("");
    try {
      const response = await api.get<{ photos: TerracePhoto[] }>(`/terraces/visits/${attendance.visit_id}/photos`, { signal: scope.current?.signal });
      if (scope.current?.signal.aborted || generation !== request.current) return;
      setPhotos(response.data.photos.filter(photo => photo.status !== "REMOVED")); setLoaded(true);
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
    // Retries retain the original file, consent, caption and UUID after an uncertain response.
    const fresh = drafts.filter(draft => !draft.attempted);
    const invalid = fresh.length ? validatePhotoSelection(fresh.map(d => d.file), occupiedPhotoSlots(photos)) : null;
    if (invalid) { setError(invalid); return; }
    writing.current = true; ++request.current; setBusy(true); setError(""); setMessage("");
    let sent = 0; let reviewed = false; let outcome: PhotoFeedback | undefined;
    try {
      for (const draft of drafts) {
        if (scope.current?.signal.aborted) return;
        setDrafts(current => current.map(item => item.key === draft.key ? { ...item, attempted: true } : item));
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
    } catch (e) { if (scope.current?.signal.aborted) return; outcome = uploadFeedback(sent, drafts.length, terracesError(e), false, uncertainPhotoResponse(e)); setFeedback(outcome); }
    finally { writing.current = false; if (!scope.current?.signal.aborted) { setBusy(false); await refresh(false, sent > 0 ? outcome : undefined); } }
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
  const visible = [...photos].sort((a, b) => Number(a.status === "REJECTED") - Number(b.status === "REJECTED")).slice(0, 3);
  const enlarged = photos.find(photo => photo.photo_id === selectedPhoto);
  return <section aria-label={`Photos from ${attendance.venue_name}`} className="mt-3 min-w-0 border-t border-[var(--tt-rule)] pt-3">
      <h3 className="tt-display text-2xl uppercase">From the Terraces</h3>
      {busy && <p role="status" className="text-sm">One moment...</p>}
      {error && <p role="alert" className="mt-2 text-sm font-bold text-red-800">{error}</p>}
      {message && <p role="status" className="mt-2 border-l-2 border-[var(--tt-gold)] pl-3 text-sm font-bold">{message}</p>}
      <div className="flex items-center justify-between gap-2 text-xs text-[var(--tt-muted)]"><span>{occupiedPhotoSlots(photos)} of 3 photos</span><button type="button" disabled={busy} onClick={() => void refresh()} className="min-h-11 underline">Refresh photos</button></div>
      {loaded && <>
        {!photos.length && !drafts.length && <p className="text-sm text-[var(--tt-muted)]">Nothing here yet.</p>}
        <div className="grid grid-cols-3 items-start gap-2">
        {visible.map(photo => <article key={photo.photo_id} className="min-w-0">
          <TerracePhotoView photo={photo} refresh={() => void refresh()} showContext={false} compact onOpen={() => setSelectedPhoto(photo.photo_id)} />
          <p className="mt-1 text-xs font-bold">{photo.status === "PENDING" ? "Waiting for review" : photo.status === "APPROVED" ? photo.published_at ? "Live" : "Approved for sharing" : "Rejected"}</p>
          {photo.caption && <p className="mt-1 break-words text-xs">{photo.caption}</p>}
          <button type="button" disabled={busy} aria-label={`Remove photo ${visible.indexOf(photo) + 1}`} onClick={() => void remove(photo)} className="min-h-11 text-xs font-bold underline">REMOVE PHOTO</button>
        </article>)}
        </div>
        {enlarged && <div className="mt-3"><button type="button" onClick={() => setSelectedPhoto(null)} className="min-h-11 text-sm font-bold underline">Close photo</button><TerracePhotoView photo={enlarged} refresh={() => void refresh()} showContext={false} /></div>}
        {occupiedPhotoSlots(photos) < 3 && drafts.length === 0 && <div className="mt-2">
          <input ref={picker} aria-label="Choose photographs" type="file" multiple accept="image/jpeg,image/png,image/heic,image/heif,.heic,.heif" disabled={busy} tabIndex={-1} className="sr-only" onChange={event => {
            const files = Array.from(event.target.files ?? []); const invalid = validatePhotoSelection(files, occupiedPhotoSlots(photos)); setError(invalid ?? "");
            if (!invalid) { setDrafts(files.map(file => ({ file, caption: "", key: crypto.randomUUID(), attempted: false }))); setConsent(false); setMessage(""); } event.target.value = "";
          }} />
          <button type="button" disabled={busy} onClick={() => picker.current?.click()} className="tt-action tt-action-secondary w-full px-3">ADD PHOTOS</button>
          <p className="mt-1 text-xs text-[var(--tt-muted)]">JPEG, PNG, HEIC or HEIF &middot; 10 MB each.</p>
        </div>}
        {occupiedPhotoSlots(photos) >= 3 && !drafts.length && <p className="mt-2 text-xs text-[var(--tt-muted)]">You&apos;ve reached the limit (3 of 3).</p>}
        {drafts.some(draft => draft.attempted) && <p className="text-sm font-bold">Try these photos again</p>}
        {drafts.map((draft, index) => <div key={draft.key} className="grid min-w-0 grid-cols-[5rem_minmax(0,1fr)] items-start gap-3">
          <div className="min-w-0"><TerracePhotoPreview file={draft.file} />{draft.attempted && <p className="break-all text-xs text-[var(--tt-muted)]">{draft.file.name}</p>}</div>
          <div className="min-w-0"><label className="grid min-w-0 gap-1 text-sm font-bold">Caption {index + 1} (optional)<textarea value={draft.caption} disabled={busy || draft.attempted} maxLength={200} rows={2} className="tt-control w-full min-w-0 p-2 font-normal" onChange={event => setDrafts(current => current.map(item => item.key === draft.key ? { ...item, caption: event.target.value } : item))} /><span className="text-xs font-normal">{draft.caption.length}/200</span></label>
          {!draft.attempted && <button type="button" disabled={busy} onClick={() => setDrafts(current => current.filter(item => item.key !== draft.key))} className="min-h-11 text-xs text-[var(--tt-muted)] underline">Remove selection {index + 1}</button>}</div>
        </div>)}
        {drafts.length > 0 && <>
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={consent} disabled={busy || drafts.some(d => d.attempted)} onChange={event => setConsent(event.target.checked)} className="mt-1 h-5 w-5 shrink-0" /><span>I took these photographs or have permission to share them. I agree to public sharing on Matchgoer with my display name after moderation.</span></label>
          <button type="button" disabled={busy || !consent} onClick={() => void submit()} className="tt-action w-full px-3">{busy ? "Sending…" : drafts.some(d => d.attempted) ? "TRY AGAIN" : "SHARE YOUR PHOTOS"}</button>
          {!drafts.some(d => d.attempted) && <button type="button" disabled={busy} onClick={() => { setDrafts([]); setConsent(false); }} className="min-h-11 text-sm font-bold underline">Cancel selection</button>}
        </>}
      </>}
  </section>;
}
