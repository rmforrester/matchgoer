"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";

import InterestedTab from "../components/InterestedTab";
import VisitedTab from "../components/VisitedTab";
import { trackEvent } from "../../lib/analytics";

function MyFootballContent() {
  const searchParams = useSearchParams();
  const activeTab =
    searchParams.get("tab") === "interested"
      ? "interested"
      : "visited";
  useEffect(() => {
    if (activeTab !== "visited") return;
    const record = () => trackEvent("my_grounds_engagement", { surface: "my_grounds" }, "view");
    record();
    window.addEventListener("matchgoer-analytics-ready", record);
    return () => window.removeEventListener("matchgoer-analytics-ready", record);
  }, [activeTab]);

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
