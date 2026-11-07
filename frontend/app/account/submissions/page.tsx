"use client";
import { useState } from "react";
import TipReviews from "@/app/components/TipReviews";
import Link from "next/link";
import { useAuth } from "@/app/components/AuthProvider";
import TerraceModeration from "@/app/components/TerraceModeration";

export default function SubmissionsPage() {
  const { accountKey } = useAuth();
  return <SubmissionsContent key={accountKey} />;
}

function SubmissionsContent() {
  const [review, setReview] = useState<"photo" | "tip">("photo");
  return <main className="mx-auto w-full max-w-xl px-4 py-5 sm:px-6">
    <p className="text-xs font-extrabold uppercase tracking-wide text-[var(--brand-interactive)]">From the Terraces</p>
    <h1 className="tt-display mt-2 text-4xl leading-none">Manage Submissions</h1>
    <nav aria-label="Review type" className="mt-4 grid grid-cols-2 gap-2">
      <button type="button" aria-pressed={review === "photo"} onClick={() => setReview("photo")} className={`tt-action min-h-11 px-2 text-xs ${review === "photo" ? "" : "tt-action-secondary"}`}>Photo Reviews</button>
      <button type="button" aria-pressed={review === "tip"} onClick={() => setReview("tip")} className={`tt-action min-h-11 px-2 text-xs ${review === "tip" ? "" : "tt-action-secondary"}`}>Tip Reviews</button>
    </nav>
    {review === "photo" ? <TerraceModeration /> : <TipReviews />}
    <Link href="/account" className="mt-3 inline-flex min-h-11 items-center text-sm font-bold underline">Back to My Account</Link>
  </main>;
}
