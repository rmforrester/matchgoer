"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import TerracePublicGallery from "../components/TerracePublicGallery";

function PhotographyPage() {
  const value = useSearchParams().get("venue");
  const venueId = value && /^[1-9][0-9]*$/.test(value) && Number.isSafeInteger(Number(value)) ? Number(value) : undefined;
  if (value !== null && !venueId) return <main className="mx-auto max-w-4xl p-4"><h1 className="tt-display text-4xl">From the Terraces</h1><p className="mt-3">We couldn&apos;t find that ground.</p></main>;
  return <main className="mx-auto min-w-0 max-w-4xl px-4 py-5 sm:px-6">
    <TerracePublicGallery key={venueId ?? "all"} venueId={venueId} />
  </main>;
}

export default function FromTheTerracesPage() {
  return <Suspense fallback={<p role="status" className="p-4">Loading photos…</p>}><PhotographyPage /></Suspense>;
}
