"use client";
import { useEffect, useState } from "react";
import { analyticsChoiceEvent, openAnalyticsPreferences, readConsent, withdrawAnalytics, type Consent } from "@/lib/analytics";

export default function AnalyticsPreferences() {
  const [choice, setChoice] = useState<Consent | null>(null);
  useEffect(() => {
    const update = () => setChoice(readConsent());
    const timer = window.setTimeout(update, 0);
    window.addEventListener(analyticsChoiceEvent, update); window.addEventListener("storage", update);
    return () => { window.clearTimeout(timer); window.removeEventListener(analyticsChoiceEvent, update); window.removeEventListener("storage", update); };
  }, []);
  return <div className="space-y-2"><p className="text-sm">Analytics: <strong>{choice === "accepted" ? "Allowed" : choice === "rejected" ? "Off" : "Not chosen"}</strong>. Your choice does not affect using Matchgoer.</p><button type="button" onClick={openAnalyticsPreferences} className="min-h-11 font-bold underline underline-offset-4">Change analytics choice</button>{choice === "accepted" && <button type="button" onClick={withdrawAnalytics} className="ml-4 min-h-11 font-bold underline underline-offset-4">Withdraw consent</button>}</div>;
}
