"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import TerracePublicGallery from "../components/TerracePublicGallery";

function PhotographyPage() {
  const value = useSearchParams().get("venue");
  const venueId = value && /^[1-9][0-9]*$/.test(value) && Number.isSafeInteger(Number(value)) ? Number(value) : undefined;
  if (value !== null && !venueId) return <main className="mx-auto max-w-4xl p-4"><h1 className="tt-display text-4xl">From the Terraces</h1><p className="mt-3">We couldn&apos;t find that ground.</p></main>;
  return <main className="mx-auto min-w-0 max-w-4xl px-4 py-5 sm:px-6">
    <header className="bg-[var(--brand-interactive)] p-4 text-[var(--tt-paper)] sm:p-6">
      <p className="text-xs font-bold uppercase tracking-widest">From the Terraces</p>
      <h1 className="tt-display mt-2 text-4xl leading-none sm:text-5xl">FOOTBALL THROUGH YOUR EYES</h1>
      <p className="mt-2 text-sm">Real moments. Real grounds. A global matchday view.</p>
    </header>
    <TerracePublicGallery key={venueId ?? "all"} venueId={venueId} />
  </main>;
}

export default function FromTheTerracesPage() {
  return <Suspense fallback={<p role="status" className="p-4">Loading photos…</p>}><PhotographyPage /></Suspense>;
}
