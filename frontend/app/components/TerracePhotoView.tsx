"use client";
import type { TerracePhoto } from "@/lib/terraces";

export default function TerracePhotoView({ photo, refresh, showContext = true }: { photo: TerracePhoto; refresh: () => void; showContext?: boolean }) {
  return <figure className="min-w-0">
    {photo.image_url ? <>
      {/* Private 90-second signed URLs must not enter a public optimisation cache. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={photo.image_url} alt={photo.caption || "Submitted matchday photograph"} referrerPolicy="no-referrer" className="h-auto max-h-[65vh] w-full object-contain" />
      <button type="button" onClick={refresh} className="min-h-11 text-xs text-[var(--tt-muted)] underline">Refresh photo</button>
    </> : <p className="py-4 text-sm text-[var(--tt-muted)]">{photo.upload_state === "incomplete" ? "This photo hasn't come through yet. Try sharing it again." : "Can't show this photo right now."}</p>}
    <figcaption className="break-words text-sm">
      {photo.caption && <p className="font-bold">{photo.caption}</p>}
      {showContext && <><p>{photo.home_team && photo.away_team ? `${photo.home_team} v ${photo.away_team}` : "Historical matchday"}</p>
      <p>Match date: {photo.match_date ? photo.match_date.slice(0, 10) : "Not recorded"}</p></>}
      {photo.submitted_at && <p className="text-[var(--tt-muted)]">Submitted: {photo.submitted_at.slice(0, 10)}</p>}
    </figcaption>
  </figure>;
}
