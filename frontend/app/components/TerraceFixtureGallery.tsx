"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { anonymousApi } from "../../lib/api";
import type { TerracePhoto } from "../../lib/terraces";
import { formatMatchDate } from "../../lib/terraces-dates";
import TerracePhotoView from "./TerracePhotoView";

type Props = { photos: TerracePhoto[]; location?: string; onPhotos: (anchor: TerracePhoto, photos: TerracePhoto[]) => void; open: (photo: TerracePhoto) => void; refresh: (photo: TerracePhoto) => void };

export default function TerraceFixtureGallery({ photos, location, onPhotos, open, refresh }: Props) {
  const anchor = photos[0];
  const { photo_id: anchorId, fixture_id: fixtureId, venue_id: venueId } = anchor;
  const card = useRef<HTMLElement>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        // Two bounded requests per visible gallery: existing eligible count and
        // at most four signed previews. Never crawl the fixture or global feed.
        const [{ data: detail }, { data: page }] = await Promise.all([
          anonymousApi.get<TerracePhoto>(`/terraces/photos/${anchorId}`, { signal: controller.signal }),
          anonymousApi.get<{ photos: TerracePhoto[] }>("/terraces/photos", { params: { limit: 4, ...(fixtureId !== null ? { fixture_id: fixtureId, venue_id: venueId } : { matchday_of: anchorId }) }, signal: controller.signal }),
        ]);
        if (controller.signal.aborted) return;
        if (page.photos.some(p => p.fixture_id !== fixtureId || (fixtureId === null && p.venue_id !== venueId))) throw new Error("Unexpected matchday");
        setTotal(Number.isInteger(detail.matchday_photo_count) && detail.matchday_photo_count! > 0 ? detail.matchday_photo_count! : null);
        setError(false); onPhotos(detail, [detail, ...page.photos]);
      } catch { if (!controller.signal.aborted) setError(true); }
    };
    const observer = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting)) { observer.disconnect(); void load(); }
    }, { rootMargin: "240px" });
    if (card.current) observer.observe(card.current);
    return () => { observer.disconnect(); controller.abort(); };
  }, [anchorId, fixtureId, venueId, attempt, onPhotos]);

  const shown = photos.slice(0, 4);
  const count = shown.length;
  const fixture = anchor.home_team && anchor.away_team ? `${anchor.home_team} v ${anchor.away_team}` : anchor.fixture_id === null ? "Historical matchday" : "Match details unavailable";
  const date = formatMatchDate(anchor.match_date);
  const view = (photo: TerracePhoto) => open({ ...photo, matchday_photo_count: total ?? photo.matchday_photo_count ?? photos.length });
  const more = total === null ? null : Math.max(0, total - count);
  return <article ref={card} className="min-w-0 border-b border-[var(--tt-rule)] pb-5" aria-label={fixture}>
    <header className="mb-3 break-words">
      <h3 className="tt-display text-3xl leading-none sm:text-4xl">{fixture}</h3>
      <p className="mt-2 text-sm font-bold">{date ? <time dateTime={anchor.match_date ?? undefined}>{date}</time> : "Date not recorded"}</p>
      <p className="mt-1 text-xs text-[var(--tt-muted)]"><Link href={`/venue/${anchor.venue_id}`} className="font-bold text-[var(--brand-interactive)]">{anchor.venue_name || "View ground"}</Link>{location && <> · {location}</>}</p>
    </header>
    {count === 1 ? <TerracePhotoView photo={anchor} presentation="editorial" showContext={false} showCaption={false} onOpen={() => view(anchor)} refresh={() => refresh(anchor)} /> :
      <div data-photo-layout={count} className={`grid aspect-[4/5] max-h-[34rem] gap-1.5 ${count === 2 ? "grid-cols-1 grid-rows-2" : count === 3 ? "grid-cols-2 grid-rows-[3fr_1fr]" : "grid-cols-3 grid-rows-[3fr_1fr]"}`}>
        {shown.map((photo, index) => <button key={photo.photo_id} type="button" onClick={() => view(photo)} aria-label={`Open photograph ${index + 1} from ${fixture}, shared by ${photo.display_name}`} className={`min-h-0 min-w-0 overflow-hidden bg-[var(--tt-paper)] focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-[var(--brand-interactive)] ${index === 0 && count > 2 ? "col-span-full" : ""}`}>
          <TerracePhotoView photo={photo} compact={index > 0 && count > 2} passive presentation="mosaic" showContext={false} showCaption={false} refresh={() => refresh(photo)} />
        </button>)}
      </div>}
    {more !== null && more > 0 && <button type="button" onClick={() => view(anchor)} className="mt-3 min-h-11 text-left text-xs font-extrabold text-[var(--brand-interactive)] underline">MORE PHOTOS FROM THIS {anchor.fixture_id === null ? "MATCHDAY" : "MATCH"} ({more}) →</button>}
    {error && <button type="button" className="mt-2 min-h-11 text-left text-xs underline" onClick={() => setAttempt(value => value + 1)}>Try loading match photos again</button>}
  </article>;
}
