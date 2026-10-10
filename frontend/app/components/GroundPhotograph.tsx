"use client";

import { useState } from "react";
import { groundPhotograph } from "../../lib/ground-photographs";

export default function GroundPhotograph({ venueId }: { venueId: number }) {
  const photo = groundPhotograph(venueId);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  if (!photo || failedSrc === photo.src) return null;
  const year = photo.captureDate.match(/\b(?:19|20)\d{2}\b/)?.[0];
  const warning = /^Photographed [^.]+\. Appearance may have changed\.$/.test(photo.historicalNote) ? null : photo.historicalNote;
  // The existing notice describes proportional display scaling only, not an image edit.
  const modification = photo.modificationNote === "Resized for display; not cropped." ? null : photo.modificationNote;
  return (
    <figure className="mt-5 border border-[var(--tt-rule)]" aria-label="Ground photograph">
      {/* Commons supplies reviewed thumbnails; no additional processing service. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={photo.src} alt={photo.alt} width={photo.width} height={photo.height}
        className="block h-auto max-h-72 w-full object-contain sm:max-h-96"
        loading="lazy" decoding="async" onError={() => setFailedSrc(photo.src)} />
      <figcaption className="break-words px-3 py-1 text-xs leading-relaxed text-[var(--tt-muted)]">
        Photo: <a className="underline" href={photo.creditUrl ?? photo.sourceUrl} target="_blank" rel="noreferrer">{photo.credit}</a>
        {photo.creditUrl && <>{" · "}<a className="underline" href={photo.sourceUrl} target="_blank" rel="noreferrer">Source</a></>}
        {" · "}<a className="underline" href={photo.licenseUrl} target="_blank" rel="noreferrer">{photo.license}</a>
        {year && <> · {year}</>}
        {modification && <> · {modification}</>}
        {warning && <> · {warning}</>}
      </figcaption>
    </figure>
  );
}
