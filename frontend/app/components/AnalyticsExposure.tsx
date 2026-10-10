"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { trackEvent } from "../../lib/analytics";

export default function AnalyticsExposure({ section, children }: { section: "decide" | "know"; children: ReactNode }) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!element.current) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const stop = () => { clearTimeout(timer); timer = undefined; };
    const observer = new IntersectionObserver(entries => {
      stop();
      if (entries[0].intersectionRatio >= 0.25 && document.visibilityState === "visible") timer = setTimeout(() => {
        trackEvent(section === "decide" ? "decide_engagement" : "know_engagement", { section, action: "exposure" }, section);
      }, 3000);
    }, { threshold: 0.25 });
    observer.observe(element.current);
    const restart = () => { stop(); if (element.current) { observer.unobserve(element.current); observer.observe(element.current); } };
    document.addEventListener("visibilitychange", restart);
    window.addEventListener("matchgoer-analytics-ready", restart);
    return () => { stop(); observer.disconnect(); document.removeEventListener("visibilitychange", restart); window.removeEventListener("matchgoer-analytics-ready", restart); };
  }, [section]);
  return <div ref={element}>{children}</div>;
}
