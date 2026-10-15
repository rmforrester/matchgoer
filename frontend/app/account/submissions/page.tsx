"use client";
import Link from "next/link";
import { useAuth } from "@/app/components/AuthProvider";
import TerraceModeration from "@/app/components/TerraceModeration";

export default function SubmissionsPage() {
  const { accountKey } = useAuth();
  return <main className="mx-auto w-full max-w-xl px-4 py-5 sm:px-6">
    <p className="text-xs font-extrabold uppercase tracking-wide text-[var(--brand-interactive)]">From the Terraces</p>
    <h1 className="tt-display mt-2 text-4xl leading-none">Manage Submissions</h1>
    <TerraceModeration key={accountKey} />
    <Link href="/account" className="mt-3 inline-flex min-h-11 items-center text-sm font-bold underline">Back to My Account</Link>
  </main>;
}
