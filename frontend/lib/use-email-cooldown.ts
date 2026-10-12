"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Provider rate limits remain authoritative; this prevents rapid repeat clicks.
export function useEmailCooldown(kind: "signup" | "recovery") {
  const key = `matchgoer.auth.${kind}-cooldown`;
  const [remaining, setRemaining] = useState(0);
  const localDeadline = useRef(0);
  useEffect(() => {
    const tick = () => {
      let deadline = localDeadline.current;
      try { deadline = Math.max(deadline, Number(sessionStorage.getItem(key)) || 0); } catch { /* Storage unavailable. */ }
      setRemaining(Math.max(0, Math.ceil((deadline - Date.now()) / 1000)));
    };
    const initial = window.setTimeout(tick, 0);
    const interval = window.setInterval(tick, 1000);
    return () => { window.clearTimeout(initial); window.clearInterval(interval); };
  }, [key]);
  const start = useCallback(() => {
    localDeadline.current = Date.now() + 60_000;
    try { sessionStorage.setItem(key, String(localDeadline.current)); } catch { /* Provider still enforces limits. */ }
    setRemaining(60);
  }, [key]);
  return { remaining, start };
}
