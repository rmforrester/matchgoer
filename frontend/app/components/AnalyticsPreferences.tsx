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
  return <div><p className="mb-2 text-sm">Analytics: <strong>{choice === "accepted" ? "Allowed" : choice === "rejected" ? "Off" : "Not chosen"}</strong>. Your choice does not affect using Matchgoer.</p><button type="button" onClick={() => choice === "accepted" ? withdrawAnalytics() : openAnalyticsPreferences(true)} className="block min-h-11 w-full text-left font-bold underline underline-offset-4 focus-visible:outline-2">{choice === "accepted" ? "WITHDRAW CONSENT" : "ALLOW ANALYTICS"}</button></div>;
}
