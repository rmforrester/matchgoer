"use client";

import axios from "axios";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import api, { anonymousApi } from "../../lib/api";
import type { TerracePhoto } from "../../lib/terraces";
import { useAuth } from "./AuthProvider";
import TerracePhotoView from "./TerracePhotoView";

type PhotoPage = { photos: TerracePhoto[]; next_cursor: string | null };
type Props = { mode?: "feed" | "preview" | "venue"; venueId?: number };
const dateLabel = (value: string) => new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

export default function TerracePublicGallery(props: Props) {
  const { accountKey } = useAuth();
  return <PublicGalleryContent key={accountKey} {...props} />;
}

function PublicGalleryContent({ mode = "feed", venueId }: Props) {
  const { authenticated } = useAuth();
  const [photos, setPhotos] = useState<TerracePhoto[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<TerracePhoto | null>(null);
  const [detailError, setDetailError] = useState("");
  const [reason, setReason] = useState("");
  const [reportMessage, setReportMessage] = useState("");
  const [reporting, setReporting] = useState(false);
  const busy = useRef(false);
  const scope = useRef<AbortController | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const selectedId = useRef<number | null>(null);
  const limit = mode === "feed" ? 12 : mode === "preview" ? 2 : 4;
  const destination = `/from-the-terraces${venueId ? `?venue=${venueId}` : ""}`;

  const load = useCallback(async (after?: string) => {
    if (busy.current) return;
    busy.current = true; setLoading(true); setError("");
    const controller = scope.current;
    try {
      // Public reads never carry a bearer token, even for an owner/moderator.
      const { data } = await anonymousApi.get<PhotoPage>("/terraces/photos", { params: { limit, venue_id: venueId, cursor: after }, signal: controller?.signal });
      if (controller?.signal.aborted) return;
      setPhotos(current => after ? [...new Map([...current, ...data.photos].map(photo => [photo.photo_id, photo])).values()] : data.photos);
      setCursor(data.next_cursor);
    } catch (failure) {
      if (controller?.signal.aborted) return;
      setError(axios.isAxiosError(failure) && failure.response?.status === 404 ? "Photo browsing isn't available here yet." : "Can't load the photos right now. Try again in a moment.");
    } finally { if (!controller?.signal.aborted) { busy.current = false; setLoading(false); } }
  }, [limit, venueId]);

  useEffect(() => {
    scope.current = new AbortController();
    void load();
    return () => { scope.current?.abort(); busy.current = false; };
  }, [load]);

  const refresh = async (photo: TerracePhoto) => {
    const controller = scope.current;
    try {
      const { data } = await anonymousApi.get<TerracePhoto>(`/terraces/photos/${photo.photo_id}`, { signal: controller?.signal });
      if (controller?.signal.aborted) return;
      setPhotos(current => current.map(item => item.photo_id === data.photo_id ? data : item));
      setSelected(current => current?.photo_id === data.photo_id ? data : current);
      setDetailError("");
    } catch (failure) {
      if (controller?.signal.aborted) return;
      if (axios.isAxiosError(failure) && failure.response?.status === 404) {
        setPhotos(current => current.filter(item => item.photo_id !== photo.photo_id));
        setSelected(current => current?.photo_id === photo.photo_id ? null : current);
        if (selectedId.current === photo.photo_id) dialog.current?.close();
      } else if (selectedId.current === photo.photo_id) setDetailError("Can't load that photo right now. Try again in a moment.");
    }
  };
  const open = (photo: TerracePhoto) => {
    opener.current = document.activeElement as HTMLElement;
    selectedId.current = photo.photo_id;
    setSelected(photo); setDetailError(""); setReason(""); setReportMessage("");
    dialog.current?.showModal();
    void refresh(photo);
  };
  const report = async () => {
    if (!selected || reporting || !reason.trim()) return;
    const photoId = selected.photo_id;
    setReporting(true); setReportMessage("");
    try {
      await api.post(`/terraces/photos/${photoId}/reports`, { reason: reason.trim() }, { signal: scope.current?.signal });
      setReportMessage("Report sent. We'll take a look."); setReason("");
    } catch { setReportMessage("Couldn't send your report. Check you're signed in with a verified account and try again."); }
    finally { setReporting(false); }
  };
  const context = (photo: TerracePhoto) => <>
    <Link href={`/venue/${photo.venue_id}`} className="font-bold underline">{photo.venue_name || "View ground"}</Link>
    {photo.home_team && photo.away_team && <p className="mt-1 text-sm">{photo.home_team} v {photo.away_team}</p>}
    {photo.match_date && <p className="mt-1 text-xs text-[var(--tt-muted)]">Match date: {dateLabel(photo.match_date)}</p>}
    {photo.caption && <p className="mt-2 break-words text-sm">{photo.caption}</p>}
    <p className="mt-2 text-xs text-[var(--tt-muted)]">{photo.display_name}{photo.published_at && <> · Published {dateLabel(photo.published_at)}</>}</p>
  </>;

  if (mode !== "feed" && photos.length === 0) return null;
  return <section className="mt-6 min-w-0 border-t-2 border-[var(--tt-ink)] pt-4" aria-label={mode === "venue" ? "Supporter photographs from this ground" : "From the Terraces photographs"}>
    {mode !== "feed" && <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 className="tt-display text-2xl">FROM THE TERRACES</h2><Link href={destination} className="inline-flex min-h-11 items-center text-xs font-bold underline">{mode === "venue" ? "MORE FROM THIS GROUND →" : "VIEW ALL →"}</Link></div>}
    {photos.length > 0 && <div className={`grid gap-5 ${mode === "feed" ? "sm:grid-cols-2" : "grid-cols-2"}`}>
      {photos.map(photo => <article key={photo.photo_id} className="min-w-0">
        <TerracePhotoView photo={photo} compact onOpen={() => open(photo)} refresh={() => void refresh(photo)} />
        <div className="mt-2 break-words">{mode === "feed" ? context(photo) : <Link href={`/venue/${photo.venue_id}`} className="text-sm font-bold underline">{photo.venue_name || "View ground"}</Link>}</div>
      </article>)}
    </div>}
    {mode === "feed" && <>
      {loading && <p role="status" className="py-4 text-sm">Loading photos…</p>}
      {!loading && !error && photos.length === 0 && <p className="py-4">Nothing here yet.</p>}
      {error && <div className="py-3"><p role="alert" className="text-sm">{error}</p><button type="button" onClick={() => void load(photos.length ? cursor ?? undefined : undefined)} className="min-h-11 font-bold underline">Try again</button></div>}
      {cursor && !error && <button type="button" disabled={loading} onClick={() => void load(cursor)} className="tt-action mt-5 min-h-11 px-5">{loading ? "Loading…" : "MORE PHOTOS"}</button>}
    </>}
    <dialog ref={dialog} onClose={() => { selectedId.current = null; setSelected(null); opener.current?.focus(); }} aria-label="From the Terraces photo" className="m-auto max-h-[90dvh] w-[calc(100%-2rem)] max-w-3xl overflow-auto bg-[var(--tt-paper)] p-4 text-[var(--tt-ink)] backdrop:bg-black/70">
      <button type="button" onClick={() => dialog.current?.close()} className="mb-2 min-h-11 font-bold underline">Close photo</button>
      {selected && <><TerracePhotoView photo={selected} showContext={false} showCaption={false} refresh={() => void refresh(selected)} /><div className="mt-3">{context(selected)}</div>
        {detailError && <p role="alert" className="mt-2 text-sm">{detailError}</p>}
        {authenticated ? <details className="mt-3"><summary className="min-h-11 cursor-pointer content-center text-sm underline">Report photo</summary><label className="grid gap-2 text-sm">What should we know?<textarea value={reason} onChange={event => setReason(event.target.value)} maxLength={200} className="tt-control p-2" /></label><button type="button" disabled={reporting || !reason.trim()} onClick={() => void report()} className="min-h-11 text-sm font-bold underline">{reporting ? "Sending…" : "SEND REPORT"}</button>{reportMessage && <p role="status" className="text-sm">{reportMessage}</p>}</details> : <Link href="/signin" className="mt-3 inline-flex min-h-11 items-center text-sm underline">Sign in to report a photo</Link>}
      </>}
    </dialog>
  </section>;
}
