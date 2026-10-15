"use client";
import { useState } from "react";
import type { TerracePhoto } from "@/lib/terraces";

export default function TerracePhotoView({ photo, refresh, showContext = true, compact = false, onOpen, showCaption = true }: { photo: TerracePhoto; refresh: () => void; showContext?: boolean; compact?: boolean; onOpen?: () => void; showCaption?: boolean }) {
  const [failed, setFailed] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const source = compact ? photo.thumbnail_url || photo.image_url : photo.image_url;
  const unavailable = !source || failed === source;
  if (compact && unavailable && onOpen) return <figure className="min-w-0"><button type="button" onClick={onOpen} aria-label="View photo details" className="aspect-square min-h-11 w-full bg-[var(--tt-paper)] px-1 text-xs underline">Photo unavailable. View details.</button></figure>;
  const image = source && !unavailable ? <>
    {/* Private URLs bypass public image optimisation and are never logged. */}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img key={`${source}:${attempt}`} src={source} alt={photo.caption || "Matchday photograph"} referrerPolicy="no-referrer" onError={() => setFailed(source)} className={compact ? "aspect-square w-full object-cover" : "h-auto max-h-[65vh] w-full object-contain"} />
  </> : null;
  return <figure className="min-w-0">
    {image && (compact && onOpen ? <button type="button" aria-label="View larger photograph" onClick={onOpen} className="block w-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">{image}</button> : image)}
    {unavailable && <p role="status" className={compact ? "break-words text-xs" : "py-2 text-sm"}>{photo.upload_state === "incomplete" ? "This photo hasn't come through yet." : "Couldn't load this photo. Try again."}</p>}
    {unavailable && <button type="button" onClick={() => { setFailed(null); setAttempt(value => value + 1); refresh(); }} className="min-h-11 text-xs text-[var(--tt-muted)] underline">Try loading photo again</button>}
    {!compact && <figcaption className="break-words text-sm">
      {showCaption && photo.caption && <p className="font-bold">{photo.caption}</p>}
      {showContext && <><p>{photo.home_team && photo.away_team ? `${photo.home_team} v ${photo.away_team}` : "Historical matchday"}</p>
      <p>{photo.venue_name || "Ground not recorded"}</p>
      <p>Match date: {photo.match_date ? photo.match_date.slice(0, 10) : "Not recorded"}</p></>}
      {showContext && photo.submitted_at && <p className="text-[var(--tt-muted)]">Submitted: {photo.submitted_at.slice(0, 10)}</p>}
    </figcaption>}
  </figure>;
}
