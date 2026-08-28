import { googleMapsDirectionsUrl } from "../../lib/venue-guide";

type Venue = { name: string; address?: string | null; city: string; country: string; capacity: number | null; latitude?: number | null; longitude?: number | null };

type Props = { venue: Venue; clubName?: string | null };

export default function VenueHeader({ venue, clubName }: Props) {
  return (
    <header className="tt-panel overflow-hidden" aria-labelledby="venue-heading">
      <div className="border-b-2 border-[var(--tt-ink)] bg-[var(--tt-blue)] px-4 py-3 text-[var(--tt-paper)] sm:px-7"><p className="text-xs font-extrabold uppercase tracking-[0.14em]">01 / The ground</p></div>
      <div className="min-w-0 px-4 py-6 sm:px-7 sm:py-8">
        <div className="min-w-0">
          <h1 id="venue-heading" className="tt-display break-words text-[clamp(3.2rem,10vw,7rem)] leading-[0.82]">{venue.name}</h1>
          {clubName && <p className="mt-4 text-lg font-extrabold">{clubName}</p>}
          <p className="mt-5 font-extrabold uppercase tracking-[0.1em] text-[var(--tt-blue)]">{venue.city}{venue.country ? ` · ${venue.country}` : ""}</p>
          {venue.address && <p className="mt-2 font-bold">{venue.address}</p>}
          {venue.latitude != null && venue.longitude != null && <a id="directions" className="mt-4 inline-flex min-h-11 items-center bg-[var(--tt-blue)] px-4 text-xs font-extrabold uppercase tracking-[0.08em] text-white" href={googleMapsDirectionsUrl(venue.latitude, venue.longitude)} target="_blank" rel="noreferrer">Directions →</a>}
          {venue.capacity !== null && venue.capacity > 0 && <p className="mt-2 text-xs font-bold uppercase tracking-[0.1em] text-[var(--tt-muted)]">Capacity · {venue.capacity.toLocaleString()}</p>}
        </div>
      </div>
    </header>
  );
}
