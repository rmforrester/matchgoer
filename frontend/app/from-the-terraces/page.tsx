"use client";

import Link from "next/link";
import { useAuth } from "../components/AuthProvider";
import { signinRoute } from "../../lib/auth-flow";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import TerracePublicGallery from "../components/TerracePublicGallery";

function PhotographyPage() {
  const params = useSearchParams();
  const value = params.get("venue");
  const { authenticated, accountKey } = useAuth();
  const [personal, setPersonal] = useState(() => params.get("view") === "your-matchdays");
  const venueId = value && /^[1-9][0-9]*$/.test(value) && Number.isSafeInteger(Number(value)) ? Number(value) : undefined;
  if (value !== null && !venueId) return <main className="mx-auto max-w-4xl p-4"><h1 className="tt-display text-4xl">From the Terraces</h1><p className="mt-3">We couldn&apos;t find that ground.</p></main>;
  return <main className="mx-auto min-w-0 max-w-4xl px-4 py-5 sm:px-6">
    <div role="group" aria-label="Photo view" className="mb-4 grid grid-cols-2 border-b border-[var(--tt-rule)]">
      {([false, true] as const).map(own => <button key={String(own)} type="button" aria-pressed={personal === own} onClick={() => setPersonal(own)} className={`min-h-11 px-1 text-xs font-extrabold focus-visible:outline-2 focus-visible:outline-[var(--brand-interactive)] ${personal === own ? "border-b-2 border-[var(--brand-interactive)] text-[var(--brand-interactive)]" : "text-[var(--tt-muted)]"}`}>{own ? "YOUR MATCHDAYS" : "ALL MATCHGOERS"}</button>)}
    </div>
    {personal && !authenticated ? <section className="py-4"><h1 className="tt-display text-3xl">YOUR MATCHDAYS</h1><p className="mt-3">Sign in to see approved photos from matches you recorded as Went.</p><Link href={signinRoute(`/from-the-terraces?view=your-matchdays${venueId ? `&venue=${venueId}` : ""}`)} className="tt-action mt-4 inline-flex items-center px-4">SIGN IN</Link></section> : <TerracePublicGallery key={`${accountKey}:${personal}:${venueId ?? "all"}`} venueId={venueId} personal={personal} />}
  </main>;
}

export default function FromTheTerracesPage() {
  return <Suspense fallback={<p role="status" className="p-4">Loading photos…</p>}><PhotographyPage /></Suspense>;
}
