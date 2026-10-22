"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/app/components/AuthProvider";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { beginGoogleSignin, googleSigninEnabled } from "@/lib/google-signin";

export default function GoogleSignInButton({ returnTo, handoffToken, convertAnonymous, disabled = false, onBusyChange }: {
  returnTo: string; handoffToken?: string; convertAnonymous?: boolean; disabled?: boolean; onBusyChange: (busy: boolean) => void;
}) {
  const { authenticated, loading } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    function returned(event: PageTransitionEvent) {
      if (event.persisted) { setBusy(false); onBusyChange(false); }
    }
    window.addEventListener("pageshow", returned);
    return () => window.removeEventListener("pageshow", returned);
  }, [onBusyChange]);
  if (!googleSigninEnabled() || authenticated) return null;

  async function start() {
    if (busy || disabled || loading) return;
    const client = getSupabaseBrowserClient();
    if (!client) { setError("Account services are unavailable right now."); return; }
    setBusy(true); onBusyChange(true); setError("");
    try { await beginGoogleSignin(client, window.location.origin, returnTo, handoffToken, convertAnonymous); }
    catch { setBusy(false); onBusyChange(false); setError("We couldn't start Google sign-in. Try again or use email and password. Your saved history remains unchanged."); }
  }

  return <div className="mt-6 grid gap-3 border-t border-[var(--tt-rule)] pt-5">
    <button type="button" disabled={busy || disabled || loading} onClick={() => void start()} className="tt-action tt-action-secondary w-full px-3 text-center" aria-busy={busy}>
      {busy ? "Opening Google…" : "CONTINUE WITH GOOGLE"}
    </button>
    {error && <p role="alert" className="text-sm font-bold text-red-800">{error}</p>}
  </div>;
}
