"use client";

import { useState } from "react";
import { groundPhotograph } from "../../lib/ground-photographs";

export default function GroundPhotograph({ venueId }: { venueId: number }) {
  const photo = groundPhotograph(venueId);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  if (!photo || failedSrc === photo.src) return null;
  return (
    <figure className="mt-5 border border-[var(--tt-rule)]" aria-label="Ground photograph">
      {/* Commons supplies reviewed thumbnails; no additional processing service. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={photo.src} alt={photo.alt} width={photo.width} height={photo.height}
        className="block h-auto max-h-72 w-full object-contain sm:max-h-96"
        loading="lazy" decoding="async" onError={() => setFailedSrc(photo.src)} />
      <figcaption className="break-words border-t border-[var(--tt-rule)] px-3 py-2 text-xs leading-relaxed text-[var(--tt-muted)]">
        <span className="block">{photo.historicalNote}</span>
        Photo: {photo.creditUrl ? <a className="underline" href={photo.creditUrl} target="_blank" rel="noreferrer">{photo.credit}</a> : photo.credit}
        {" · "}<a className="underline" href={photo.sourceUrl} target="_blank" rel="noreferrer">Wikimedia Commons</a>
        {" · "}<a className="underline" href={photo.licenseUrl} target="_blank" rel="noreferrer">{photo.license}</a>
        {" · "}{photo.modificationNote}
      </figcaption>
    </figure>
  );
}
