"use client";

import Link from "next/link";
import Script from "next/script";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { acceptAnalytics, configureAnalytics, consentKey, measurementId, readConsent, safePage, setAnalyticsEnabled, trackPage, withdrawAnalytics, type Consent } from "../../lib/analytics";

export default function AnalyticsConsent() {
  const pathname = usePathname();
  const [consent, setConsent] = useState<Consent | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => { setConsent(readConsent()); setLoaded(true); }, 0);
    const sync = (event: StorageEvent) => { if (event.key === consentKey && readConsent() !== "accepted") withdrawAnalytics(); };
    window.addEventListener("storage", sync);
    return () => { clearTimeout(timer); window.removeEventListener("storage", sync); };
  }, []);
  useEffect(() => {
    setAnalyticsEnabled(consent === "accepted" && Boolean(safePage(pathname)));
    if (consent === "accepted" && safePage(pathname)) { configureAnalytics(); trackPage(pathname); }
  }, [consent, pathname, ready]);

  const choose = (value: Consent) => {
    if (value === "accepted") acceptAnalytics();
    if (value === "rejected") setAnalyticsEnabled(false);
    try { localStorage.setItem(consentKey, value); } catch { /* This choice applies to this page only. */ }
    setConsent(value);
  };

  return <>
    {consent === "accepted" && safePage(pathname) && <Script id="matchgoer-ga4" src={`https://www.googletagmanager.com/gtag/js?id=${measurementId}`} strategy="afterInteractive" onReady={() => setReady(true)} />}
    <footer className="mt-auto border-t border-[var(--tt-rule)] bg-[var(--tt-paper)] px-4 py-4 text-xs text-[var(--tt-muted)]">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-2">
        <Link href="/privacy" className="min-h-11 content-center underline">Privacy & cookies</Link>
        {loaded && (consent === "accepted" ? <button type="button" onClick={() => { withdrawAnalytics(); setConsent("rejected"); }} className="min-h-11 underline">Withdraw analytics consent</button> : consent === "rejected" ? <button type="button" onClick={() => setConsent(null)} className="min-h-11 underline">Analytics preferences</button> : null)}
      </div>
      {loaded && consent === null && <section aria-label="Analytics preferences" className="mx-auto mt-2 max-w-6xl border border-[var(--brand-interactive)] p-4">
        <h2 className="tt-display text-xl font-extrabold uppercase text-[var(--brand-interactive)]">Help improve Matchgoer</h2>
        <p className="mt-2 max-w-2xl text-sm">With your permission, Google Analytics helps us understand how Matchgoer is used. Your choice won&apos;t affect the football you find. No advertising tracking.</p>
        <div className="mt-3 flex flex-wrap gap-3">{(["accepted", "rejected"] as const).map(value => <button key={value} type="button" onClick={() => choose(value)} className="min-h-11 border border-[var(--brand-interactive)] px-5 font-extrabold uppercase text-[var(--brand-interactive)]">{value === "accepted" ? "Accept analytics" : "Reject analytics"}</button>)}</div>
      </section>}
    </footer>
  </>;
}
