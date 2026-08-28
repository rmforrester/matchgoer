"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import AccountShell from "@/app/components/AccountShell";
import { authCallbackRoute, completeAuthenticatedFlow, safeReturnTo, signinRoute, userFacingAuthError } from "@/lib/auth-flow";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { clearConversionHandoffAfter, loadConversionHandoff } from "@/lib/account-conversion-checkpoint";

export default function AuthCallback({ code, returnTo: requestedReturnTo, handoffToken, providerError }: { code?: string; returnTo?: string; handoffToken?: string; providerError?: string }) {
  const router = useRouter();
  const [error, setError] = useState(providerError ? "The confirmation link could not be completed." : "");
  const returnTo = safeReturnTo(requestedReturnTo);

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
        if (code) {
          const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
          if (exchangeError) throw exchangeError;
        }
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (sessionError) throw sessionError;
        if (!data.session) throw new Error("Confirmation did not create a session");
        const checkpoint = loadConversionHandoff();
        const conversionToken = handoffToken ?? checkpoint?.token;
        const destination = await clearConversionHandoffAfter(
          completeAuthenticatedFlow(data.session, checkpoint?.returnTo ?? returnTo, conversionToken),
        );
        if (!cancelled) router.replace(destination.route);
      } catch (requestError) {
        if (!cancelled) setError(userFacingAuthError(requestError, "We couldn't finish account setup. Sign in to continue."));
      }
    })();
    return () => { cancelled = true; };
  }, [code, handoffToken, providerError, returnTo, router]);

  return <AccountShell kicker="Account setup" title={error ? "Setup paused" : "Saving your football"} intro={error || "Your email is confirmed. We're keeping your Matchgoer history with your new account."}>
    {error ? <div className="mt-6 flex flex-wrap gap-3"><a href={authCallbackRoute(returnTo, handoffToken)} className="tt-action inline-flex items-center justify-center px-5">Try again →</a><a href={signinRoute(returnTo, handoffToken)} className="tt-action tt-action-secondary inline-flex items-center justify-center px-5">Sign in</a></div> : <p role="status" className="mt-6 font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)]">Finishing account setup…</p>}
  </AccountShell>;
}
