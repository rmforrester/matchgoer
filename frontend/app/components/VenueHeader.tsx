type Venue = { name: string; address?: string | null; city: string; country: string; capacity: number | null; latitude?: number | null; longitude?: number | null };

type Props = { venue: Venue; score?: number | null; reviewCount?: number; recommendPercentage?: number | null };

export default function VenueHeader({ venue, score, reviewCount = 0, recommendPercentage }: Props) {
  const hasRating = reviewCount > 0 && score !== undefined && score !== null;
  return (
    <header className="tt-panel overflow-hidden" aria-labelledby="venue-heading">
      <div className="border-b-2 border-[var(--tt-ink)] bg-[var(--tt-blue)] px-4 py-3 text-[var(--tt-paper)] sm:px-7"><p className="text-xs font-extrabold uppercase tracking-[0.14em]">01 / The ground</p></div>
      <div className="grid min-w-0 gap-6 px-4 py-6 sm:px-7 sm:py-8 lg:grid-cols-[minmax(0,1fr)_17rem] lg:items-end">
        <div className="min-w-0">
          <h1 id="venue-heading" className="tt-display break-words text-[clamp(3.2rem,10vw,7rem)] leading-[0.82]">{venue.name}</h1>
          <p className="mt-5 font-extrabold uppercase tracking-[0.1em] text-[var(--tt-blue)]">{venue.city}{venue.country ? ` · ${venue.country}` : ""}</p>
          {venue.address && <p className="mt-2 font-bold">{venue.address}</p>}
          {venue.latitude != null && venue.longitude != null && <a className="mt-3 inline-block text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)] underline decoration-2 underline-offset-4" href={`https://www.openstreetmap.org/?mlat=${venue.latitude}&mlon=${venue.longitude}#map=16/${venue.latitude}/${venue.longitude}`} target="_blank" rel="noreferrer">Map & directions →</a>}
          {venue.capacity !== null && venue.capacity > 0 && <p className="mt-2 text-xs font-bold uppercase tracking-[0.1em] text-[var(--tt-muted)]">Capacity · {venue.capacity.toLocaleString()}</p>}
        </div>
        <div className="border-t-2 border-[var(--tt-ink)] pt-4 lg:border-l-2 lg:border-t-0 lg:pl-6 lg:pt-0">
          <p className="tt-kicker">Terrace Rating</p>
          {hasRating ? <><p className="tt-display mt-1 text-6xl leading-none">{score.toFixed(1)}</p><p className="mt-2 text-xs font-bold uppercase tracking-[0.08em] text-[var(--tt-muted)]">From {reviewCount} supporter {reviewCount === 1 ? "review" : "reviews"}</p>{recommendPercentage !== undefined && recommendPercentage !== null && <p className="mt-4 border-t border-[var(--tt-rule)] pt-3 text-sm font-extrabold uppercase tracking-[0.08em]">{Math.round(recommendPercentage)}% would recommend</p>}</> : <><p className="tt-display mt-1 text-5xl leading-none text-[var(--tt-muted)]">Unrated</p><p className="mt-2 text-xs leading-5 text-[var(--tt-muted)]">No supporter rating yet.</p></>}
        </div>
      </div>
    </header>
  );
}
