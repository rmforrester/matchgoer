"use client";

import { coordinatePlaceUrl } from "../../lib/map-destination";

export default function MapDirections({ latitude, longitude, name = "", className = "" }: { latitude: number | null; longitude: number | null; name?: string; className?: string }) {
  if (latitude == null || longitude == null) return null;
  const apple = coordinatePlaceUrl(latitude, longitude, name, "apple");
  const google = coordinatePlaceUrl(latitude, longitude, name, "google");
  if (!apple || !google) return null;
  return <details className={`relative ${className}`}>
    <summary className="tt-action tt-action-secondary inline-flex min-h-11 cursor-pointer items-center justify-center px-3 text-xs">Directions</summary>
    <div className="absolute left-0 top-full z-30 mt-1 grid min-w-40 border border-[var(--tt-rule)] bg-[var(--tt-paper)] p-1 shadow-md" aria-label="Choose directions provider">
      <a className="min-h-11 content-center px-3 text-sm font-bold underline" href={apple} target="_blank" rel="noopener noreferrer">Apple Maps</a>
      <a className="min-h-11 content-center px-3 text-sm font-bold underline" href={google} target="_blank" rel="noopener noreferrer">Google Maps</a>
    </div>
  </details>;
}
