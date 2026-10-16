"use client";

import axios from "axios";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import api, { anonymousApi } from "../../lib/api";
import { mergePublicPhotos, groupPublicPhotos } from "../../lib/terraces-groups";
import { publicMatchdayParams, viewerStepIndex } from "../../lib/terraces-viewer";
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
  const reportRequest = useRef(0);
  const [matchdayPhotos, setMatchdayPhotos] = useState<TerracePhoto[]>([]);
  const [matchdayCursor, setMatchdayCursor] = useState<string | null>(null);
  const [matchdayLoaded, setMatchdayLoaded] = useState(false);
  const [matchdayTotal, setMatchdayTotal] = useState(1);
  const [matchdayLoading, setMatchdayLoading] = useState(false);
  const [matchdayError, setMatchdayError] = useState("");
  const [moving, setMoving] = useState(false);
  const matchdaySource = useRef<TerracePhoto | null>(null);
  const viewerScope = useRef<AbortController | null>(null);
  const viewerRun = useRef(0);
  const pageBusy = useRef(false);
  const moveBusy = useRef(false);
  const matchdayStarted = useRef(false);
  const swipe = useRef<{ id: number; x: number; y: number } | null>(null);
  const limit = mode === "feed" ? 12 : mode === "preview" ? 5 : 4;
  const destination = `/from-the-terraces${venueId ? `?venue=${venueId}` : ""}`;

  const load = useCallback(async (after?: string) => {
    if (busy.current) return;
    busy.current = true; setLoading(true); setError("");
    const controller = scope.current;
    try {
      // Public reads never carry a bearer token, even for an owner/moderator.
      const { data } = await anonymousApi.get<PhotoPage>("/terraces/photos", { params: { limit, venue_id: venueId, cursor: after, selection: mode === "preview" ? "discover" : undefined }, signal: controller?.signal });
      if (controller?.signal.aborted) return;
      setPhotos(current => after ? mergePublicPhotos(current, data.photos) : data.photos);
      setCursor(data.next_cursor);
    } catch (failure) {
      if (controller?.signal.aborted) return;
      setError(axios.isAxiosError(failure) && failure.response?.status === 404 ? "Photo browsing isn't available here yet." : "Can't load the photos right now. Try again in a moment.");
    } finally { if (!controller?.signal.aborted) { busy.current = false; setLoading(false); } }
  }, [limit, venueId, mode]);

  useEffect(() => {
    scope.current = new AbortController();
    void load();
    return () => { scope.current?.abort(); viewerScope.current?.abort(); busy.current = false; };
  }, [load]);

  useEffect(() => {
    const controller = scope.current;
    for (const photo of (mode === "preview" ? photos.slice(0, 5) : groupPublicPhotos(photos).map(group => group[0]))) {
      if (requestedVenues.current.has(photo.venue_id)) continue;
      requestedVenues.current.add(photo.venue_id);
      void anonymousApi.get<{ city?: string | null; country?: string | null }>(`/venue/${photo.venue_id}`, { signal: controller?.signal }).then(({ data }) => {
        if (controller?.signal.aborted) return;
        const location = [...new Set([data.city?.trim(), data.country?.trim()].filter(Boolean))].join(", ");
        setLocations(current => ({ ...current, [photo.venue_id]: location }));
      }).catch(() => { /* Missing canonical location is simply omitted. */ });
    }
  }, [mode, photos]);

  const loadMatchday = async (after?: string): Promise<TerracePhoto[] | null> => {
    const anchor = matchdaySource.current, controller = viewerScope.current, run = viewerRun.current;
    if (!anchor || pageBusy.current || controller?.signal.aborted) return null;
    pageBusy.current = true; setMatchdayLoading(true); setMatchdayError("");
    try {
      const { data } = await anonymousApi.get<PhotoPage>("/terraces/photos", { params: publicMatchdayParams(anchor, after), signal: controller?.signal });
      if (controller?.signal.aborted || run !== viewerRun.current) return null;
      setMatchdayPhotos(current => mergePublicPhotos(after ? current : [], data.photos));
      setMatchdayCursor(data.next_cursor); setMatchdayLoaded(true);
      return data.photos;
    } catch (failure) {
      if (!controller?.signal.aborted && run === viewerRun.current) setMatchdayError(axios.isAxiosError(failure) && failure.response?.status === 404 ? "These photos are no longer available." : "Can't load these photos right now. Try again in a moment.");
      return null;
    } finally { if (run === viewerRun.current) { pageBusy.current = false; setMatchdayLoading(false); } }
  };
  const startMatchday = (photo: TerracePhoto) => {
    if (mode !== "preview" || matchdayStarted.current || (photo.matchday_photo_count ?? 1) <= 1) return;
    matchdaySource.current = photo; matchdayStarted.current = true;
    void loadMatchday();
  };
  const refresh = async (photo: TerracePhoto) => {
    const controller = scope.current;
    const run = viewerRun.current;
    try {
      const { data } = await anonymousApi.get<TerracePhoto>(`/terraces/photos/${photo.photo_id}`, { signal: controller?.signal });
      if (controller?.signal.aborted) return;
      setPhotos(current => current.map(item => item.photo_id === data.photo_id ? data : item));
      if (run === viewerRun.current) setMatchdayPhotos(current => current.map(item => item.photo_id === data.photo_id ? data : item));
      if (run === viewerRun.current && selectedId.current === data.photo_id) {
        setSelected(data); setMatchdayTotal(data.matchday_photo_count ?? 1); startMatchday(data);
      }
      if (run === viewerRun.current && selectedId.current === data.photo_id) setDetailError("");
    } catch (failure) {
      if (controller?.signal.aborted) return;
      if (axios.isAxiosError(failure) && failure.response?.status === 404) {
        setPhotos(current => current.filter(item => item.photo_id !== photo.photo_id));
        if (run === viewerRun.current) {
          setMatchdayPhotos(current => current.filter(item => item.photo_id !== photo.photo_id));
          setSelected(current => current?.photo_id === photo.photo_id ? null : current);
          if (selectedId.current === photo.photo_id) dialog.current?.close();
        }
      } else if (run === viewerRun.current && selectedId.current === photo.photo_id) setDetailError("Can't load that photo right now. Try again in a moment.");
    }
  };
  const open = (photo: TerracePhoto) => {
    viewerScope.current?.abort(); viewerScope.current = new AbortController(); viewerRun.current += 1;
    pageBusy.current = false; moveBusy.current = false; matchdayStarted.current = false;
    matchdaySource.current = null; setMatchdayPhotos([]); setMatchdayCursor(null); setMatchdayLoaded(false);
    setMatchdayTotal(photo.matchday_photo_count ?? 1); setMatchdayLoading(false); setMatchdayError(""); setMoving(false);
    reportRequest.current += 1; setReporting(false);
      opener.current = document.activeElement as HTMLElement;
    selectedId.current = photo.photo_id;
    setSelected(photo); setDetailError(""); setReason(""); setReportMessage("");
    dialog.current?.showModal();
    startMatchday(photo);
    void refresh(photo);
  };
  const move = async (step: -1 | 1) => {
    if (!selected || !matchdaySource.current || pageBusy.current || moveBusy.current) return;
    const run = viewerRun.current, controller = viewerScope.current;
    let rows = matchdayPhotos, index = viewerStepIndex(rows, selected.photo_id, step);
    moveBusy.current = true; setMoving(true); setDetailError("");
    try {
      if (index === null && step === 1 && matchdayCursor) {
        const page = await loadMatchday(matchdayCursor);
        if (page === null || run !== viewerRun.current || controller?.signal.aborted) return;
        rows = mergePublicPhotos(rows, page); index = viewerStepIndex(rows, selected.photo_id, step);
      }
      if (index === null) return;
      const next = rows[index];
      // Recheck eligibility and refresh the signed image before showing cached pages.
      const { data } = await anonymousApi.get<TerracePhoto>(`/terraces/photos/${next.photo_id}`, { signal: controller?.signal });
      if (run !== viewerRun.current || controller?.signal.aborted) return;
      reportRequest.current += 1; setReporting(false);
      selectedId.current = data.photo_id; setSelected(data);
      setMatchdayPhotos(current => current.map(item => item.photo_id === data.photo_id ? data : item));
      setPhotos(current => current.map(item => item.photo_id === data.photo_id ? data : item));
      setMatchdayTotal(data.matchday_photo_count ?? matchdayTotal); setReason(""); setReportMessage("");
    } catch (failure) {
      if (run !== viewerRun.current || controller?.signal.aborted) return;
      if (axios.isAxiosError(failure) && failure.response?.status === 404 && index !== null) {
        const removed = rows[index].photo_id;
        setMatchdayPhotos(current => current.filter(item => item.photo_id !== removed));
        setPhotos(current => current.filter(item => item.photo_id !== removed));
        setMatchdayTotal(current => Math.max(1, current - 1));
        setDetailError("That photo is no longer available.");
      } else setDetailError("Can't load that photo right now. Try again in a moment.");
    } finally { if (run === viewerRun.current) { moveBusy.current = false; setMoving(false); } }
  };
  const report = async () => {
    if (!selected || reporting || !reason.trim()) return;
    const photoId = selected.photo_id;
    const attempt = ++reportRequest.current, run = viewerRun.current;
    const current = () => attempt === reportRequest.current && run === viewerRun.current && selectedId.current === photoId && !scope.current?.signal.aborted;
    setReporting(true); setReportMessage("");
    try {
      await api.post(`/terraces/photos/${photoId}/reports`, { reason: reason.trim() }, { signal: scope.current?.signal });
      if (current()) { setReportMessage("Report sent. We'll take a look."); setReason(""); }
    } catch { if (current()) setReportMessage("Couldn't send your report. Check you're signed in with a verified account and try again."); }
    finally { if (current()) setReporting(false); }
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

  const grouped = mode === "feed" && !venueId;
  const groups = groupPublicPhotos(photos);
  const feedPhotos = mode === "preview" ? photos.slice(0, 5) : photos;
  const matchdayIndex = selected ? matchdayPhotos.findIndex(photo => photo.photo_id === selected.photo_id) : -1;
  const observedTotal = matchdayLoaded && !matchdayCursor ? Math.max(1, matchdayPhotos.length) : matchdayTotal;
  const multiple = mode === "preview" && observedTotal > 1;
  const navigationBusy = matchdayLoading || moving;
  const previousAvailable = matchdayIndex > 0 && !navigationBusy;
  const nextAvailable = (matchdayPhotos.length > matchdayIndex + 1 || !!matchdayCursor) && !navigationBusy;
  if (mode !== "feed" && photos.length === 0) return null;
  return <section className={mode === "feed" ? "min-w-0" : "mt-6 min-w-0 border-t-2 border-[var(--tt-ink)] pt-4"} aria-label={mode === "venue" ? "Supporter photographs from this ground" : "From the Terraces photographs"}>
    {mode === "feed" && <header><h1 tabIndex={-1} className="tt-display text-4xl leading-none sm:text-5xl">FROM THE TERRACES</h1><h2 className="mt-3 text-xs font-bold tracking-widest">LATEST PHOTOS</h2></header>}
    {mode !== "feed" && <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 className="tt-display text-2xl">FROM THE TERRACES</h2><Link href={destination} className="inline-flex min-h-11 items-center text-xs font-bold underline">{mode === "venue" ? "MORE FROM THIS GROUND →" : "VIEW ALL →"}</Link></div>}
    {feedPhotos.length > 0 && <div role={mode === "preview" ? "group" : undefined} aria-label={mode === "preview" ? "Recent photographs" : undefined} tabIndex={mode === "preview" ? 0 : undefined} className={mode === "preview" ? "flex snap-x snap-proximity items-start gap-3 overflow-x-auto overscroll-x-contain px-1 pb-2 pt-1 focus-visible:outline-2 focus-visible:outline-[var(--brand-interactive)]" : `grid items-start gap-5 ${mode === "feed" ? "mt-3 sm:grid-cols-2" : photos.length === 1 ? "grid-cols-1" : "grid-cols-2"}`}>
      {grouped ? groups.map(group => <GroundPhotoGroup key={group[0].venue_id} photos={group} location={locations[group[0].venue_id]} getSignal={() => scope.current?.signal} onPhotos={incoming => setPhotos(current => mergePublicPhotos(current, incoming))} open={open} refresh={photo => void refresh(photo)} />) : feedPhotos.map(photo => <article key={photo.photo_id} className={`min-w-0 ${mode === "preview" ? "max-w-52 shrink-0 basis-[42%] snap-start" : ""}`}>
        {mode === "preview" ? <button type="button" onClick={() => open(photo)} aria-label={`View photograph from ${photo.venue_name || "this ground"}${photo.home_team && photo.away_team ? `, ${photo.home_team} v ${photo.away_team}` : ""}${(photo.matchday_photo_count ?? 0) > 1 ? `, ${photo.matchday_photo_count! - 1} more ${photo.matchday_photo_count === 2 ? "photo" : "photos"} from this matchday` : ""}`} className="block min-h-11 w-full text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">
          <span className="relative block">
            <TerracePhotoView photo={photo} compact passive showContext={false} showCaption={false} refresh={() => void refresh(photo)} />
            {(photo.matchday_photo_count ?? 0) > 1 && <span aria-hidden="true" className="absolute bottom-2 right-2 bg-black/85 px-2 py-1 text-xs font-bold text-white">+{photo.matchday_photo_count! - 1} more</span>}
          </span>
          <span className="mt-2 block break-words text-sm font-extrabold">{photo.home_team && photo.away_team ? `${photo.home_team} v ${photo.away_team}` : photo.venue_name || "Ground"}</span>
          <span className="mt-1 block break-words text-xs text-[var(--tt-muted)]">{photo.home_team && photo.away_team && photo.venue_name}{photo.home_team && photo.away_team && photo.venue_name && locations[photo.venue_id] && " · "}{locations[photo.venue_id]}</span>
        </button> : <>
        <TerracePhotoView photo={photo} compact={mode === "venue" && photos.length > 1} presentation={mode === "feed" || photos.length === 1 ? "editorial" : "default"} showContext={false} showCaption={false} onOpen={() => open(photo)} refresh={() => void refresh(photo)} />
        {mode === "feed" && <div className="mt-2 break-words">{context(photo)}</div>}
        </>}
      </article>)}
    </div>}
    {mode === "feed" && <>
      {loading && <p role="status" className="py-4 text-sm">Loading photos…</p>}
      {!loading && !error && photos.length === 0 && <p className="py-4">Nothing here yet.</p>}
      {error && <div className="py-3"><p role="alert" className="text-sm">{error}</p><button type="button" onClick={() => void load(photos.length ? cursor ?? undefined : undefined)} className="min-h-11 font-bold underline">Try again</button></div>}
      {cursor && !error && <button type="button" disabled={loading} onClick={() => void load(cursor)} className="tt-action mt-5 min-h-11 px-5">{loading ? "Loading…" : "MORE PHOTOS"}</button>}
    </>}
    <dialog ref={dialog} onClose={() => { reportRequest.current += 1; setReporting(false); viewerScope.current?.abort(); viewerRun.current += 1; selectedId.current = null; setSelected(null); if (opener.current?.isConnected) opener.current.focus(); else document.querySelector<HTMLElement>("h1")?.focus(); }} onKeyDown={event => { if (!multiple || event.altKey || event.ctrlKey || event.metaKey || (event.target as HTMLElement).closest("input,textarea,select,[contenteditable=true]")) return; if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); if (event.key === "ArrowLeft" ? previousAvailable : nextAvailable) void move(event.key === "ArrowLeft" ? -1 : 1); } }} aria-label="From the Terraces photo" className="fixed inset-0 m-0 h-dvh max-h-none w-full max-w-none overflow-auto bg-black p-4 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))] text-white backdrop:bg-black">
      <div className="mx-auto max-w-6xl">
      <button type="button" aria-label="Close photo" onClick={() => dialog.current?.close()} className="sticky top-0 z-10 mb-2 min-h-11 bg-black px-2 text-sm font-bold underline focus-visible:outline-2 focus-visible:outline-white">CLOSE</button>
      {selected && <><div style={{ touchAction: multiple ? "pan-y pinch-zoom" : undefined }} onPointerDown={event => { if (!multiple || event.pointerType !== "touch" || !event.isPrimary) { swipe.current = null; return; } swipe.current = { id: event.pointerId, x: event.clientX, y: event.clientY }; event.currentTarget.setPointerCapture(event.pointerId); }} onPointerCancel={() => { swipe.current = null; }} onPointerUp={event => { const start = swipe.current; swipe.current = null; if (!start || start.id !== event.pointerId) return; const x = event.clientX - start.x, y = event.clientY - start.y; if (Math.abs(x) >= 45 && Math.abs(x) > Math.abs(y) * 1.25 && (x < 0 ? nextAvailable : previousAvailable)) void move(x < 0 ? 1 : -1); }}><TerracePhotoView key={selected.photo_id} photo={selected} presentation="immersive" showContext={false} showCaption={false} refresh={() => void refresh(selected)} /></div>
        {mode === "preview" && <>
          {multiple && <div className="mx-auto mt-2 max-w-xl" aria-busy={navigationBusy}>
            <p role="status" aria-live="polite" aria-atomic="true" className="text-center text-xs">{matchdayIndex >= 0 ? `${matchdayIndex + 1} of ${observedTotal}` : "Selected photo"}</p>
            <div className="flex justify-between gap-4"><button type="button" aria-label="Previous matchday photo" aria-disabled={!previousAvailable} onClick={() => { if (previousAvailable) void move(-1); }} className="min-h-11 min-w-11 text-xs font-bold aria-disabled:opacity-40">← PREVIOUS</button><button type="button" aria-label="Next matchday photo" aria-disabled={!nextAvailable} onClick={() => { if (nextAvailable) void move(1); }} className="min-h-11 min-w-11 text-xs font-bold aria-disabled:opacity-40">NEXT →</button></div>
          </div>}
          {navigationBusy && <p role="status" className="mt-2 text-xs">Loading photos…</p>}
          {matchdayError && <div className="mt-2 text-sm"><p role="alert">{matchdayError}</p><button type="button" onClick={() => void loadMatchday(matchdayLoaded ? matchdayCursor ?? undefined : undefined)} className="min-h-11 font-bold underline">Try again</button></div>}
        </>}
        <div className="mt-3">{context(selected, true)}</div>
        {detailError && <p role="alert" className="mt-2 text-sm">{detailError}</p>}
        {authenticated ? <details className="mt-3"><summary className="min-h-11 cursor-pointer content-center text-sm underline">Report photo</summary><label className="grid gap-2 text-sm">What should we know?<textarea value={reason} onChange={event => setReason(event.target.value)} maxLength={200} className="tt-control p-2" /></label><button type="button" disabled={reporting || !reason.trim()} onClick={() => void report()} className="min-h-11 text-sm font-bold underline">{reporting ? "Sending…" : "SEND REPORT"}</button>{reportMessage && <p role="status" className="text-sm">{reportMessage}</p>}</details> : <Link href="/signin" className="mt-3 inline-flex min-h-11 items-center text-sm underline">Sign in to report a photo</Link>}
      </>}
      </div>
    </dialog>
  </section>;
}


function GroundPhotoGroup({ photos, location, getSignal, onPhotos, open, refresh }: { photos: TerracePhoto[]; location?: string; getSignal: () => AbortSignal | undefined; onPhotos: (photos: TerracePhoto[]) => void; open: (photo: TerracePhoto) => void; refresh: (photo: TerracePhoto) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const busy = useRef(false);
  const control = useRef<HTMLButtonElement>(null);
  const photo = photos[0];
  const id = `ground-photos-${photo.venue_id}`;
  const fixture = photo.home_team && photo.away_team ? `${photo.home_team} v ${photo.away_team}` : null;
  const load = async () => {
    const signal = getSignal();
    if (busy.current || cursor === null || signal?.aborted) return;
    busy.current = true; setLoading(true); setError("");
    try {
      const { data } = await anonymousApi.get<PhotoPage>("/terraces/photos", { params: { venue_id: photo.venue_id, limit: 24, cursor }, signal });
      if (signal?.aborted) return;
      onPhotos(data.photos); setCursor(data.next_cursor);
    } catch { if (!signal?.aborted) setError("Can't load the photos right now. Try again in a moment."); }
    finally { busy.current = false; if (!signal?.aborted) setLoading(false); }
  };
  return <article className="min-w-0">
    <header className="mb-2 break-words"><h3 className="text-base font-extrabold">{fixture || photo.venue_name || "Ground"}</h3><p className="mt-1 text-xs text-[var(--tt-muted)]">{fixture && photo.venue_name}{fixture && photo.venue_name && location && " · "}{location}</p></header>
    <TerracePhotoView photo={photo} presentation="editorial" showContext={false} showCaption={false} onOpen={() => open(photo)} refresh={() => refresh(photo)} />
    <PhotoDetails photo={photo} />
    <button ref={control} type="button" aria-expanded={expanded} aria-controls={id} onClick={() => { setExpanded(!expanded); if (!expanded && cursor === undefined) void load(); }} className="mt-2 min-h-11 text-left text-xs font-bold underline">{expanded ? "SHOW LESS" : "MORE PHOTOS FROM THIS GROUND"}</button>
    <div id={id} hidden={!expanded}>
      <div className="grid grid-cols-2 items-start gap-3">{expanded && photos.slice(1).map(item => <div key={item.photo_id} className="min-w-0"><TerracePhotoView photo={item} compact showContext={false} showCaption={false} onOpen={() => open(item)} refresh={() => refresh(item)} /><p className="mt-1 break-words text-xs font-bold">{item.home_team && item.away_team ? `${item.home_team} v ${item.away_team}` : item.venue_name || "Ground"}</p><PhotoDetails photo={item} /></div>)}</div>
      {loading && <p role="status" className="py-2 text-sm">Loading photos…</p>}
      {error && <p role="alert" className="py-2 text-sm">{error}</p>}
      {!loading && cursor === null && photos.length === 1 && <p className="py-2 text-sm">No other photos here yet.</p>}
      {(cursor || error) && <button type="button" disabled={loading} onClick={() => void load()} className="min-h-11 text-xs font-bold underline">{error ? "Try again" : "MORE PHOTOS"}</button>}
      {photos.length > 3 && <button type="button" onClick={() => { setExpanded(false); control.current?.focus(); }} className="block min-h-11 text-xs font-bold underline">SHOW LESS</button>}
    </div>
  </article>;
}
function PhotoDetails({ photo }: { photo: TerracePhoto }) {
  const date = formatMatchDate(photo.match_date), publication = formatPublicationDate(photo.published_at);
  return <div className="mt-2 break-words text-xs text-[var(--tt-muted)]">{date && <p><span className="sr-only">Match date: </span><time dateTime={photo.match_date ?? undefined}>{date}</time></p>}{photo.caption && <p className="mt-1 text-sm text-[var(--tt-ink)]">{photo.caption}</p>}<p className="mt-1">{photo.display_name}{publication && <> · <time dateTime={photo.published_at ?? undefined}>{publication}</time></>}</p></div>;
}
