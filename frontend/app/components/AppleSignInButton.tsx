"use client";

import Image from "next/image";
import { useState } from "react";
import { useAuth } from "./AuthProvider";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { appleSigninEnabled, beginAppleSignin } from "@/lib/apple-signin";

export default function AppleSignInButton({ returnTo, handoffToken, convertAnonymous, disabled = false, onBusyChange }: {
  returnTo: string; handoffToken?: string; convertAnonymous?: boolean; disabled?: boolean; onBusyChange: (busy: boolean) => void;
}) {
  const { authenticated, loading } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!appleSigninEnabled() || authenticated) return null;
  async function start() {
    const client = getSupabaseBrowserClient();
    if (busy || loading || disabled) return;
    if (!client) { setError("Account services are unavailable right now."); return; }
    setError(""); setBusy(true); onBusyChange(true);
    try { await beginAppleSignin(client, returnTo, handoffToken, convertAnonymous); }
    catch (failure) {
      setError((failure as { code?: string })?.code === "USER_CANCELLED" ? "Apple sign-in cancelled. Your saved history remains unchanged." : "We couldn't finish Apple sign-in. Try again or use email and password. Your saved history remains unchanged.");
    } finally { setBusy(false); onBusyChange(false); }
  }
  return <div className="mt-3 grid gap-2"><button type="button" disabled={busy || disabled || loading} aria-busy={busy} onClick={() => void start()}
    style={{ fontFamily: "-apple-system, BlinkMacSystemFont, sans-serif" }} className="flex min-h-11 w-full items-center justify-center gap-0 rounded-md bg-black px-3 text-[19px] font-medium text-white focus-visible:outline-2 focus-visible:outline-[var(--brand-interactive)] focus-visible:outline-offset-2 disabled:opacity-50">
    <Image src="/apple-signin-logo.png" width={44} height={44} alt="" aria-hidden="true" unoptimized className="h-11 w-11 shrink-0" />{busy ? "Opening Apple..." : "Sign in with Apple"}
  </button>{error && <p role="alert" className="text-sm font-bold text-red-800">{error}</p>}</div>;
}
