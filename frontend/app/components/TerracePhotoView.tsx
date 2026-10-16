"use client";
import { useState } from "react";
import type { TerracePhoto } from "@/lib/terraces";

export default function TerracePhotoView({ photo, refresh, showContext = true, compact = false, onOpen, showCaption = true, presentation = "default", passive = false }: { photo: TerracePhoto; refresh: () => void; showContext?: boolean; compact?: boolean; onOpen?: () => void; showCaption?: boolean; presentation?: "default" | "editorial" | "immersive"; passive?: boolean }) {
  const [failed, setFailed] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState<string | null>(null);
  const source = compact ? photo.thumbnail_url || photo.image_url : photo.image_url;
  // A confirmed POST has no signed URLs until the owned-list read completes.
  // Absence during that hand-off is delivery loading, not submission failure.
  const awaitingDelivery = !source && !photo.image_state && photo.upload_state !== "incomplete";
  const unavailable = (!source && !awaitingDelivery) || (!!source && failed === source);
  if (compact && awaitingDelivery && onOpen) return <figure className="min-w-0"><button type="button" onClick={onOpen} aria-label="View photo details" className="aspect-square min-h-11 w-full bg-[var(--tt-paper)] px-1 text-xs"><span role="status">Loading photo…</span></button></figure>;
  if (compact && unavailable && onOpen) return <figure className="min-w-0"><button type="button" onClick={onOpen} aria-label="View photo details" className="aspect-square min-h-11 w-full bg-[var(--tt-paper)] px-1 text-xs underline">Photo unavailable. View details.</button></figure>;
  const image = source && !unavailable ? <>
    {/* Private URLs bypass public image optimisation and are never logged. */}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img key={`${source}:${attempt}`} src={source} alt={photo.caption || "Matchday photograph"} loading="lazy" decoding="async" referrerPolicy="no-referrer" onLoad={() => setLoaded(`${source}:${attempt}`)} onError={() => setFailed(source)} className={`${loaded === `${source}:${attempt}` ? "" : "opacity-0"} ${compact ? "aspect-square w-full object-cover" : presentation === "default" ? "h-auto max-h-[65vh] w-full object-contain" : `mx-auto h-auto w-auto max-w-full object-contain ${presentation === "immersive" ? "max-h-[75dvh]" : "max-h-[36rem]"}`}`} />
  </> : null;
  if (passive) return <span className="relative block min-w-0">{image}{!unavailable && source && loaded !== `${source}:${attempt}` && <span role="status" className="absolute inset-0 content-center text-center text-xs">Loading photo…</span>}{(awaitingDelivery || unavailable) && <span role="status" className="block aspect-square content-center text-xs">{unavailable ? "Photo unavailable. View details." : "Loading photo…"}</span>}</span>;
  return <figure className="min-w-0">
    {!unavailable && (awaitingDelivery || (source && loaded !== `${source}:${attempt}`)) && <p role="status" className="text-xs text-[var(--tt-muted)]">Loading photo…</p>}
    {image && (onOpen ? <button type="button" aria-label="View larger photograph" onClick={onOpen} className="block w-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">{image}</button> : image)}
    {unavailable && <p role="status" className={compact ? "break-words text-xs" : "py-2 text-sm"}>{photo.upload_state === "incomplete" ? "This photo hasn't come through yet." : "Couldn't load this photo. Try again."}</p>}
    {unavailable && <button type="button" onClick={() => { setFailed(null); setAttempt(value => value + 1); refresh(); }} className="min-h-11 text-xs text-[var(--tt-muted)] underline">Try loading photo again</button>}
    {awaitingDelivery && <button type="button" onClick={refresh} className="min-h-11 text-xs underline">Load photo</button>}
    {!compact && <figcaption className="break-words text-sm">
      {showCaption && photo.caption && <p className="font-bold">{photo.caption}</p>}
      {showContext && <><p>{photo.home_team && photo.away_team ? `${photo.home_team} v ${photo.away_team}` : "Historical matchday"}</p>
      <p>{photo.venue_name || "Ground not recorded"}</p>
      <p>Match date: {photo.match_date ? photo.match_date.slice(0, 10) : "Not recorded"}</p></>}
      {showContext && photo.submitted_at && <p className="text-[var(--tt-muted)]">Submitted: {photo.submitted_at.slice(0, 10)}</p>}
    </figcaption>}
  </figure>;
}
