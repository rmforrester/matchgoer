import MapDirections from "./MapDirections";
import GroundPhotograph from "./GroundPhotograph";
import type { ReactNode } from "react";

type Venue = { venue_id: number; name: string; address?: string | null; city: string; country: string; capacity: number | null; latitude?: number | null; longitude?: number | null };

type Props = { venue: Venue; clubName?: string | null; children?: ReactNode };

export default function VenueHeader({ venue, clubName, children }: Props) {
  return (
    <header className="tt-panel" aria-labelledby="venue-heading">
      <div className="border-b-2 border-[var(--tt-ink)] bg-[var(--brand-interactive)] px-4 py-3 text-[var(--tt-paper)] sm:px-7"><p className="text-xs font-extrabold uppercase tracking-[0.14em]">01 / The ground</p></div>
      <div className="min-w-0 px-4 py-6 sm:px-7 sm:py-8">
        <div className="min-w-0">
          <h1 id="venue-heading" className="tt-display break-words text-[clamp(3.2rem,10vw,7rem)] leading-[0.82]">{venue.name}</h1>
          {children}
          {clubName && <p className="mt-4 text-lg font-extrabold">{clubName}</p>}
          <p className="mt-5 font-extrabold uppercase tracking-[0.1em] text-[var(--brand-interactive)]">{venue.city}{venue.country ? ` · ${venue.country}` : ""}</p>
          <GroundPhotograph venueId={venue.venue_id} />
          {venue.address && <p className="mt-2 font-bold">{venue.address}</p>}
          <MapDirections latitude={venue.latitude ?? null} longitude={venue.longitude ?? null} name={venue.name} className="mt-4" />
          {venue.capacity !== null && venue.capacity > 0 && <p className="mt-2 text-xs font-bold uppercase tracking-[0.1em] text-[var(--tt-muted)]">Capacity · {venue.capacity.toLocaleString()}</p>}
        </div>
      </div>
    </header>
  );
}
