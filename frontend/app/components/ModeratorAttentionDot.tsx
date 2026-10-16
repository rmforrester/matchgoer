"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "./AuthProvider";

export const MODERATION_CHANGED = "matchgoer:moderation-changed";

export default function ModeratorAttentionDot() {
  const { authenticated, loading, accountKey } = useAuth();
  return authenticated && !loading ? <AttentionForAccount key={accountKey} /> : null;
}

function AttentionForAccount() {
  const [attention, setAttention] = useState(false);
  useEffect(() => {
    let request: AbortController | undefined;
    let disposed = false;
    async function refresh() {
      if (document.visibilityState === "hidden") return;
      request?.abort();
      const current = new AbortController();
      request = current;
      try {
        // The protected queue is the capability check; never trust a client ID list.
        const pending = await api.get<{ pending_count: number }>("/terraces/moderator/photos", { params: { limit: 1 }, signal: current.signal });
        if (disposed || current.signal.aborted) return;
        const reports = await api.get<{ reports: unknown[] }>("/terraces/moderator/reports", { params: { limit: 1 }, signal: current.signal });
        if (disposed || current.signal.aborted) return;
        setAttention(pending.data.pending_count > 0 || reports.data.reports.length > 0);
      } catch {
        // No authorised result means no moderator indicator. Retry on the next event.
        if (!disposed && !current.signal.aborted) setAttention(false);
      }
    }
    void refresh();
    const returned = () => { void refresh(); };
    window.addEventListener("focus", returned);
    document.addEventListener("visibilitychange", returned);
    window.addEventListener(MODERATION_CHANGED, returned);
    return () => {
      disposed = true; request?.abort();
      window.removeEventListener("focus", returned);
      document.removeEventListener("visibilitychange", returned);
      window.removeEventListener(MODERATION_CHANGED, returned);
    };
  }, []);
  return attention ? <span role="status" aria-label="Photo moderation needs attention" className="inline-flex shrink-0"><span aria-hidden="true" className="h-2 w-2 rounded-full bg-[var(--brand-interactive)]" /><span className="sr-only">Photo moderation needs attention</span></span> : null;
}
