"use client";

import { useEffect, useState } from "react";
import api from "../../lib/api";
import { googleMapsDirectionsUrl } from "../../lib/venue-guide";

export default function FixtureDirections({ venueId }: { venueId: number | null }) {
  const [destination, setDestination] = useState<{ venueId: number; url: string } | null>(null);
  useEffect(() => {
    if (!venueId || !Number.isSafeInteger(venueId) || venueId <= 0) return;
    const controller = new AbortController();
    api.get(`/venue/${venueId}`, { signal: controller.signal }).then(({ data }) => {
      const { latitude, longitude } = data ?? {};
      if (!controller.signal.aborted && Number.isFinite(latitude) && Number.isFinite(longitude) && Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180) {
        setDestination({ venueId, url: googleMapsDirectionsUrl(latitude, longitude) });
      }
    }).catch(() => { /* No valid canonical destination: omit directions. */ });
    return () => controller.abort();
  }, [venueId]);
  const directionsUrl = destination?.venueId === venueId ? destination?.url : null;
  if (!directionsUrl) return null;
  return <a href={directionsUrl} target="_blank" rel="noopener noreferrer" aria-label="Directions to the match ground (opens in a new tab)" className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 border border-[var(--mg-green)] px-3 py-2 text-xs font-extrabold uppercase text-[var(--mg-green)] hover:bg-[var(--mg-paper)] focus-visible:-outline-offset-4">DIRECTIONS <span aria-hidden="true">&rarr;</span></a>;
}
