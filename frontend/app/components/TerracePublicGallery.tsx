"use client";

import axios from "axios";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import api, { anonymousApi } from "../../lib/api";
import type { TerracePhoto } from "../../lib/terraces";
import { useAuth } from "./AuthProvider";
import TerracePhotoView from "./TerracePhotoView";
import { formatMatchDate, formatPublicationDate } from "../../lib/terraces-dates";

type PhotoPage = { photos: TerracePhoto[]; next_cursor: string | null };
type Props = { mode?: "feed" | "preview" | "venue"; venueId?: number };

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
  const [locations, setLocations] = useState<Record<number, string>>({});
  const requestedVenues = useRef(new Set<number>());
  const busy = useRef(false);
  const scope = useRef<AbortController | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const selectedId = useRef<number | null>(null);
  const limit = mode === "feed" ? 12 : mode === "preview" ? 5 : 4;
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

  useEffect(() => {
    if (mode !== "preview") return;
    const controller = scope.current;
    for (const photo of photos.slice(0, 5)) {
      if (requestedVenues.current.has(photo.venue_id)) continue;
      requestedVenues.current.add(photo.venue_id);
      void anonymousApi.get<{ city?: string | null; country?: string | null }>(`/venue/${photo.venue_id}`, { signal: controller?.signal }).then(({ data }) => {
        if (controller?.signal.aborted) return;
        const location = [...new Set([data.city?.trim(), data.country?.trim()].filter(Boolean))].join(", ");
        setLocations(current => ({ ...current, [photo.venue_id]: location }));
      }).catch(() => { /* Missing canonical location is simply omitted. */ });
    }
  }, [mode, photos]);

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
  const context = (photo: TerracePhoto, dark = false) => {
    const matchDate = formatMatchDate(photo.match_date);
    const publication = formatPublicationDate(photo.published_at);
    const fixture = photo.home_team && photo.away_team ? `${photo.home_team} v ${photo.away_team}` : null;
    const secondary = dark ? "text-white/75" : "text-[var(--tt-muted)]";
    return <>
      {dark ? <p className="text-base font-extrabold">{photo.venue_name || "Ground"}</p> : <Link href={`/venue/${photo.venue_id}`} className="text-base font-extrabold underline">{photo.venue_name || "View ground"}</Link>}
      {(fixture || matchDate) && <p className={`mt-1 text-xs ${secondary}`}>{fixture}{fixture && matchDate && " · "}{matchDate && <><span className="sr-only">Match date: </span><time dateTime={photo.match_date ?? undefined}>{matchDate}</time></>}</p>}
      {photo.caption && <p className="mt-1 break-words text-sm">{photo.caption}</p>}
      <p className={`mt-1 text-xs ${secondary}`}><span className="sr-only">Shared by </span>{photo.display_name}{publication && <> · <span className="sr-only">Published </span><time dateTime={photo.published_at ?? undefined}>{publication}</time></>}</p>
      {dark && <Link href={`/venue/${photo.venue_id}`} className="mt-2 inline-flex min-h-11 items-center text-xs font-bold underline">VIEW GROUND →</Link>}
    </>;
  };

  const feedPhotos = mode === "preview" ? photos.slice(0, 5) : photos;
  if (mode !== "feed" && photos.length === 0) return null;
  return <section className={mode === "feed" ? "min-w-0" : "mt-6 min-w-0 border-t-2 border-[var(--tt-ink)] pt-4"} aria-label={mode === "venue" ? "Supporter photographs from this ground" : "From the Terraces photographs"}>
    {mode === "feed" && <header><h1 tabIndex={-1} className="tt-display text-4xl leading-none sm:text-5xl">FROM THE TERRACES</h1><h2 className="mt-3 text-xs font-bold tracking-widest">LATEST PHOTOS</h2></header>}
    {mode !== "feed" && <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 className="tt-display text-2xl">FROM THE TERRACES</h2><Link href={destination} className="inline-flex min-h-11 items-center text-xs font-bold underline">{mode === "venue" ? "MORE FROM THIS GROUND →" : "VIEW ALL →"}</Link></div>}
    {feedPhotos.length > 0 && <div role={mode === "preview" ? "group" : undefined} aria-label={mode === "preview" ? "Recent photographs" : undefined} tabIndex={mode === "preview" ? 0 : undefined} className={mode === "preview" ? "flex snap-x snap-proximity items-start gap-3 overflow-x-auto overscroll-x-contain px-1 pb-2 pt-1 focus-visible:outline-2 focus-visible:outline-[var(--brand-interactive)]" : `grid items-start gap-5 ${mode === "feed" ? "mt-3 sm:grid-cols-2" : "grid-cols-2"}`}>
      {feedPhotos.map(photo => <article key={photo.photo_id} className={`min-w-0 ${mode === "preview" ? "max-w-52 shrink-0 basis-[42%] snap-start" : ""}`}>
        {mode === "preview" ? <button type="button" onClick={() => open(photo)} aria-label={`View photograph from ${photo.venue_name || "this ground"}${photo.home_team && photo.away_team ? `, ${photo.home_team} v ${photo.away_team}` : ""}`} className="block min-h-11 w-full text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">
          <TerracePhotoView photo={photo} compact passive showContext={false} showCaption={false} refresh={() => void refresh(photo)} />
          <span className="mt-2 block break-words text-sm font-extrabold">{photo.venue_name || "Ground"}</span>
          {photo.home_team && photo.away_team && <span className="mt-1 block break-words text-xs text-[var(--tt-muted)]">{photo.home_team} v {photo.away_team}</span>}
          {locations[photo.venue_id] && <span className="mt-1 block break-words text-xs text-[var(--tt-muted)]">{locations[photo.venue_id]}</span>}
        </button> : <>
        <TerracePhotoView photo={photo} compact={mode !== "feed"} presentation={mode === "feed" ? "editorial" : "default"} showContext={false} showCaption={false} onOpen={() => open(photo)} refresh={() => void refresh(photo)} />
        <div className="mt-2 break-words">{mode === "feed" ? context(photo) : <Link href={`/venue/${photo.venue_id}`} className="text-sm font-bold underline">{photo.venue_name || "View ground"}</Link>}</div>
        </>}
      </article>)}
    </div>}
    {mode === "feed" && <>
      {loading && <p role="status" className="py-4 text-sm">Loading photos…</p>}
      {!loading && !error && photos.length === 0 && <p className="py-4">Nothing here yet.</p>}
      {error && <div className="py-3"><p role="alert" className="text-sm">{error}</p><button type="button" onClick={() => void load(photos.length ? cursor ?? undefined : undefined)} className="min-h-11 font-bold underline">Try again</button></div>}
      {cursor && !error && <button type="button" disabled={loading} onClick={() => void load(cursor)} className="tt-action mt-5 min-h-11 px-5">{loading ? "Loading…" : "MORE PHOTOS"}</button>}
    </>}
    <dialog ref={dialog} onClose={() => { selectedId.current = null; setSelected(null); if (opener.current?.isConnected) opener.current.focus(); else document.querySelector<HTMLElement>("h1")?.focus(); }} aria-label="From the Terraces photo" className="fixed inset-0 m-0 h-dvh max-h-none w-full max-w-none overflow-auto bg-black p-4 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))] text-white backdrop:bg-black">
      <div className="mx-auto max-w-6xl">
      <button type="button" aria-label="Close photo" onClick={() => dialog.current?.close()} className="sticky top-0 z-10 mb-2 min-h-11 bg-black px-2 text-sm font-bold underline focus-visible:outline-2 focus-visible:outline-white">CLOSE</button>
      {selected && <><TerracePhotoView photo={selected} presentation="immersive" showContext={false} showCaption={false} refresh={() => void refresh(selected)} /><div className="mt-3">{context(selected, true)}</div>
        {detailError && <p role="alert" className="mt-2 text-sm">{detailError}</p>}
        {authenticated ? <details className="mt-3"><summary className="min-h-11 cursor-pointer content-center text-sm underline">Report photo</summary><label className="grid gap-2 text-sm">What should we know?<textarea value={reason} onChange={event => setReason(event.target.value)} maxLength={200} className="tt-control p-2" /></label><button type="button" disabled={reporting || !reason.trim()} onClick={() => void report()} className="min-h-11 text-sm font-bold underline">{reporting ? "Sending…" : "SEND REPORT"}</button>{reportMessage && <p role="status" className="text-sm">{reportMessage}</p>}</details> : <Link href="/signin" className="mt-3 inline-flex min-h-11 items-center text-sm underline">Sign in to report a photo</Link>}
      </>}
      </div>
    </dialog>
  </section>;
}
