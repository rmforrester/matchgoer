"use client";
import { useRef, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "./AuthProvider";
import TerracePhotoView from "./TerracePhotoView";
import TerracePhotoPreview from "./TerracePhotoPreview";
import { uploadFeedback, refreshFailure, uncertainPhotoResponse, type PhotoFeedback } from "@/lib/terraces-feedback";
import { occupiedPhotoSlots, photoMetadata, terracesError, validatePhotoSelection, type PhotoAttendance, type TerracePhoto } from "@/lib/terraces";

type Draft = { file: File; caption: string; key: string; attempted: boolean };
export default function TerracePhotoSubmission({ attendance }: { attendance: PhotoAttendance }) {
  const { authenticated } = useAuth();
  const [open, setOpen] = useState(false);
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
  if (!authenticated) return null;
  async function refresh(clearError = true, confirmed?: PhotoFeedback) {
    const generation = ++request.current; setBusy(true); if (clearError) setError("");
    try {
      const response = await api.get<{ photos: TerracePhoto[] }>(`/terraces/visits/${attendance.visit_id}/photos`);
      if (generation !== request.current) return;
      setPhotos(response.data.photos); setLoaded(true);
    } catch (e) { if (generation === request.current) { setFeedback(confirmed ? refreshFailure(confirmed) : { kind: "error", text: terracesError(e) }); setLoaded(false); } }
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
        setDrafts(current => current.map(item => item.key === draft.key ? { ...item, attempted: true } : item));
        const result = await api.post<{ photo_id: number; status: string }>(`/terraces/visits/${attendance.visit_id}/photos`, draft.file, {
          headers: { "Content-Type": draft.file.type || "application/octet-stream", "Idempotency-Key": draft.key, "X-Terraces-Metadata": photoMetadata(draft.caption, consent) }, timeout: 60_000,
        });
        if (!["PENDING", "APPROVED"].includes(result.data.status) || !Number.isInteger(result.data.photo_id)) throw new Error("Submission not confirmed");
        sent++; reviewed ||= result.data.status === "APPROVED";
        setDrafts(current => current.filter(item => item.key !== draft.key));
      }
      outcome = uploadFeedback(sent, drafts.length, "", reviewed); setFeedback(outcome);
    } catch (e) { outcome = uploadFeedback(sent, drafts.length, terracesError(e), false, uncertainPhotoResponse(e)); setFeedback(outcome); }
    finally { writing.current = false; setBusy(false); await refresh(false, sent > 0 ? outcome : undefined); }
  }
  async function remove(photo: TerracePhoto) {
    if (writing.current) return; writing.current = true; ++request.current; setBusy(true); setError(""); setMessage("");
    try {
      const response = await api.delete(`/terraces/photos/${photo.photo_id}`);
      if (response.data.status !== "REMOVED" || response.data.photo_id !== photo.photo_id) throw new Error("Removal not confirmed");
      setPhotos(current => current.map(item => item.photo_id === photo.photo_id ? { ...item, status: "REMOVED", image_url: undefined } : item));
      setMessage("Photo removed.");
    } catch (e) { setError(terracesError(e)); }
    finally { writing.current = false; setBusy(false); }
  }
  return <div className="mt-3 min-w-0 border-t border-[var(--tt-rule)] pt-2">
    <button type="button" aria-expanded={open} aria-controls={`photos-${attendance.visit_id}`} onClick={() => { setOpen(value => !value); if (!open) void refresh(); }} className="min-h-11 text-sm font-extrabold uppercase text-[var(--brand-interactive)] underline">{open ? "Hide photos −" : "ADD PHOTOS"}</button>
    {open && <section id={`photos-${attendance.visit_id}`} aria-label={`Photos from ${attendance.venue_name}`} className="grid min-w-0 gap-2 py-1">
      <h3 className="tt-display text-2xl uppercase">From the Terraces</h3>
      {busy && <p role="status">One moment…</p>}
      {error && <p role="alert" className="text-sm font-bold text-red-800">{error}</p>}
      {message && <p role="status" className="border-l-2 border-[var(--tt-gold)] pl-3 text-sm font-bold">{message}</p>}
      <button type="button" disabled={busy} onClick={() => void refresh()} className="min-h-11 justify-self-start text-xs text-[var(--tt-muted)] underline">Refresh photos</button>
      {loaded && <>
        {!photos.length && !drafts.length && <p className="text-sm text-[var(--tt-muted)]">Nothing here yet.</p>}
        {photos.map(photo => <article key={photo.photo_id} className="min-w-0 border-t border-[var(--tt-rule)] py-3">
          <p className="mb-2 text-xs font-extrabold uppercase">{photo.status === "PENDING" ? "Waiting for review" : photo.status === "APPROVED" ? photo.published_at ? "Your photo is live!" : "Approved for sharing" : photo.status === "REJECTED" ? "This photo couldn't be shared." : "Photo removed"}</p>
          <TerracePhotoView photo={photo} refresh={() => void refresh()} showContext={false} />
          {photo.status !== "REMOVED" && <button type="button" disabled={busy} onClick={() => void remove(photo)} className="min-h-11 text-sm font-bold underline">REMOVE PHOTO</button>}
        </article>)}
        {occupiedPhotoSlots(photos) < 3 && drafts.length === 0 && <label className="grid gap-1 text-sm font-bold">Choose photographs<input type="file" multiple accept="image/jpeg,image/png,image/heic,image/heif,.heic,.heif" disabled={busy} className="min-h-11 max-w-full min-w-0 text-sm" onChange={event => {
          const files = Array.from(event.target.files ?? []); const invalid = validatePhotoSelection(files, occupiedPhotoSlots(photos)); setError(invalid ?? "");
          if (!invalid) { setDrafts(files.map(file => ({ file, caption: "", key: crypto.randomUUID(), attempted: false }))); setConsent(false); setMessage(""); } event.target.value = "";
        }} /><span className="font-normal">Up to 3 photos. JPEG, PNG, HEIC or HEIF; 10 MB each.</span></label>}
        {occupiedPhotoSlots(photos) >= 3 && !drafts.length && <p className="text-sm">You have three photos here already.</p>}
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
    </section>}
  </div>;
}
