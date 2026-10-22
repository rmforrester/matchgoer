"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import localFont from "next/font/local";
import styles from "./GoogleSignInButton.module.css";
import { useAuth } from "@/app/components/AuthProvider";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { beginGoogleSignin, googleSigninEnabled } from "@/lib/google-signin";

const googleSans = localFont({ src: "../fonts/google-sans-medium.ttf", weight: "500", style: "normal", display: "swap" });

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
    <button type="button" disabled={busy || disabled || loading} onClick={() => void start()} className={`${styles.button} ${googleSans.className}`} aria-busy={busy}>
      <Image src="/google-g.png" width={20} height={20} alt="" aria-hidden="true" unoptimized />
      <span>{busy ? "Opening Google…" : "Continue with Google"}</span>
    </button>
    {error && <p role="alert" className="text-sm font-bold text-red-800">{error}</p>}
  </div>;
}
