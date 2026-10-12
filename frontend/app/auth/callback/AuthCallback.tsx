"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import AccountShell from "@/app/components/AccountShell";
import { useAuth } from "@/app/components/AuthProvider";
import { accountRoute, authCallbackRoute, completeAuthenticatedFlow, safeReturnTo, signinRoute, userFacingAuthError } from "@/lib/auth-flow";
import { confirmationLinkError } from "@/lib/auth-reliability";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { clearConversionHandoffAfter, loadConversionHandoff } from "@/lib/account-conversion-checkpoint";

export default function AuthCallback({ code, returnTo: requestedReturnTo, handoffToken, providerError }: { code?: string; returnTo?: string; handoffToken?: string; providerError?: string }) {
  const router = useRouter();
  const { refreshAccount, isPasswordRecovery } = useAuth();
  const [error, setError] = useState(providerError ? "This confirmation link is unavailable. It may have expired or already been used. Sign in if you confirmed your email, or request a new link." : "");
  const returnTo = safeReturnTo(requestedReturnTo);
  // Routing hint only, never permission to update a password. Capture before
  // Supabase validates/removes the fragment; its recovery event can be deferred.
  const recoveryLink = useRef(typeof window !== "undefined" && new URLSearchParams(window.location.hash.slice(1)).get("type") === "recovery");

  useEffect(() => {
    if (providerError) return;
    const supabase = getSupabaseBrowserClient();
    if (!supabase) {
      window.setTimeout(() => setError("Account services are unavailable right now."), 0);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        // Let URL validation finish before deciding whether this is recovery.
        await supabase.auth.getSession();
        await new Promise(resolve => window.setTimeout(resolve, 0));
        if (cancelled) return;
        if (recoveryLink.current || isPasswordRecovery()) { router.replace(accountRoute("/auth/recovery", returnTo)); return; }
        if (code) {
          const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
          if (exchangeError) throw exchangeError;
        }
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (sessionError) throw sessionError;
        if (cancelled) return;
        if (isPasswordRecovery()) { router.replace(accountRoute("/auth/recovery", returnTo)); return; }
        if (!data.session) throw new Error("Confirmation did not create a session");
        const checkpoint = loadConversionHandoff();
        const conversionToken = handoffToken ?? checkpoint?.token;
        const destination = await clearConversionHandoffAfter(
          completeAuthenticatedFlow(data.session, checkpoint?.returnTo ?? returnTo, conversionToken),
        );
        await refreshAccount();
        if (!cancelled) router.replace(destination.route);
      } catch (requestError) {
        if (!cancelled) setError(confirmationLinkError(requestError) ? "This confirmation link has expired or already been used. Sign in if your email is confirmed, or request a new link." : userFacingAuthError(requestError, "We couldn't finish account setup. Sign in or request a new confirmation link. Your saved history remains unchanged."));
      }
    })();
    return () => { cancelled = true; };
  }, [code, handoffToken, isPasswordRecovery, providerError, refreshAccount, returnTo, router]);

  return <AccountShell kicker="Account setup" title={error ? "Setup paused" : "Saving your football"} intro={error || "Checking your confirmation and keeping your saved history with you."}>
    {error ? <div className="mt-6 grid gap-3"><a href={signinRoute(returnTo, handoffToken)} className="tt-action inline-flex items-center justify-center px-5">Sign in</a><a href={accountRoute("/auth/confirm", returnTo)} className="tt-action tt-action-secondary inline-flex items-center justify-center px-5">Request a new confirmation link</a><a href={authCallbackRoute(returnTo, handoffToken)} className="min-h-11 content-center text-sm underline">Retry account setup</a></div> : <p role="status" className="mt-6 font-extrabold uppercase tracking-[0.08em] text-[var(--brand-interactive)]">Finishing account setup…</p>}
  </AccountShell>;
}
