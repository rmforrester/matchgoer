"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import AccountShell from "@/app/components/AccountShell";
import { accountRoute, completeAuthenticatedFlow, safeReturnTo, userFacingAuthError } from "@/lib/auth-flow";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { clearConversionHandoff, loadConversionHandoff } from "@/lib/account-conversion-checkpoint";

export default function AuthCallback({ code, returnTo: requestedReturnTo, providerError }: { code?: string; returnTo?: string; providerError?: string }) {
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
        const destination = await completeAuthenticatedFlow(data.session, checkpoint?.returnTo ?? returnTo, checkpoint?.token);
        clearConversionHandoff();
        if (!cancelled) router.replace(destination.route);
      } catch (requestError) {
        if (!cancelled) setError(userFacingAuthError(requestError, "We couldn't finish account setup. Sign in to continue."));
      }
    })();
    return () => { cancelled = true; };
  }, [code, providerError, returnTo, router]);

  return <AccountShell kicker="Account setup" title={error ? "Setup paused" : "Saving your football"} intro={error || "Your email is confirmed. We're keeping your Matchgoer history with your new account."}>
    {error ? <div className="mt-6 flex flex-wrap gap-3"><a href={accountRoute("/auth/callback", returnTo)} className="tt-action inline-flex items-center justify-center px-5">Try again →</a><a href={accountRoute("/signin", returnTo)} className="tt-action tt-action-secondary inline-flex items-center justify-center px-5">Sign in</a></div> : <p role="status" className="mt-6 font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)]">Finishing account setup…</p>}
  </AccountShell>;
}
