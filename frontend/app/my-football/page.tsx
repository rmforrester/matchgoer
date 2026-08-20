"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import InterestedTab from "../components/InterestedTab";
import VisitedTab from "../components/VisitedTab";

function MyFootballContent() {
  const searchParams = useSearchParams();
  const activeTab =
    searchParams.get("tab") === "interested"
      ? "interested"
      : "visited";

  return activeTab === "interested" ? <InterestedTab /> : <VisitedTab />;
}

export default function MyFootballPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
          <p className="font-semibold text-[var(--tt-muted)]">Loading your football…</p>
        </main>
      }
    >
      <MyFootballContent />
    </Suspense>
  );
}
