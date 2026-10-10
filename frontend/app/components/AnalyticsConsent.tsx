"use client";

import Link from "next/link";
import Script from "next/script";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { acceptAnalytics, configureAnalytics, consentKey, measurementId, readConsent, safePage, setAnalyticsEnabled, trackPage, withdrawAnalytics, type Consent } from "../../lib/analytics";

export default function AnalyticsConsent() {
  const pathname = usePathname();
  const [consent, setConsent] = useState<Consent | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [ready, setReady] = useState(false);
  const panelRef = useRef<HTMLElement>(null);
  const [panelHeight, setPanelHeight] = useState(0);
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const root = document.documentElement;
    const previousPadding = root.style.scrollPaddingBottom;
    const measure = () => {
      const height = Math.ceil(panel.getBoundingClientRect().height);
      setPanelHeight(height);
      root.style.scrollPaddingBottom = `${height + 16}px`;
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(panel, { box: "border-box" });
    return () => { observer.disconnect(); root.style.scrollPaddingBottom = previousPadding; };
  }, [loaded, consent]);
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
      {loaded && consent === null && <>
        <div aria-hidden="true" style={{ height: panelHeight }} />
        <section ref={panelRef} aria-labelledby="analytics-consent-heading" aria-describedby="analytics-consent-description" className="fixed inset-x-0 bottom-0 z-[1100] max-h-[calc(100dvh-10rem)] overflow-y-auto border-t-2 border-[var(--brand-interactive)] bg-[var(--tt-paper)] pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] pt-4 pb-[max(1rem,env(safe-area-inset-bottom))] text-[var(--tt-ink)] sm:pt-5">
          <div className="mx-auto max-w-3xl">
            <h2 id="analytics-consent-heading" className="tt-display text-2xl font-extrabold uppercase text-[var(--brand-interactive)]">Help shape Matchgoer</h2>
            <div id="analytics-consent-description" className="mt-2 space-y-2 text-sm leading-5">
              <p>You&apos;re helping us build a better matchday companion.</p>
              <p>We&apos;re testing Matchgoer with a small group of football supporters. With your permission, we&apos;d like to understand how you use the app so we can improve finding, choosing and attending football.</p>
              <p>We won&apos;t use analytics to track your personal matchday history.</p>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3">{(["accepted", "rejected"] as const).map(value => <button key={value} type="button" onClick={() => choose(value)} className="min-h-11 border border-[var(--brand-interactive)] px-3 py-2 font-extrabold uppercase text-[var(--brand-interactive)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-interactive)]">{value === "accepted" ? "Accept analytics" : "No thanks"}</button>)}</div>
            <p className="mt-3 text-xs leading-5 text-[var(--tt-muted)]">You can change your choice at any time. <Link href="/privacy" className="inline-block min-h-11 content-center underline">Privacy & cookies</Link></p>
          </div>
        </section>
      </>}
    </footer>
  </>;
}
