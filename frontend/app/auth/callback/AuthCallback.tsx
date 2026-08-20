"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import AccountShell from "@/app/components/AccountShell";
import { accountRoute, completeAuthenticatedFlow, safeReturnTo, userFacingAuthError } from "@/lib/auth-flow";
import { getSupabaseBrowserClient } from "@/lib/supabase";

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
        const destination = await completeAuthenticatedFlow(data.session, returnTo);
        if (!cancelled) router.replace(destination.route);
      } catch (requestError) {
        if (!cancelled) setError(userFacingAuthError(requestError, "We couldn't finish account setup. Sign in to continue."));
      }
    })();
    return () => { cancelled = true; };
  }, [code, providerError, returnTo, router]);

  return <AccountShell kicker="Account setup" title={error ? "Setup paused" : "Saving your football"} intro={error || "Your email is confirmed. We're keeping your Terrace Talk history with your new account."}>
    {error ? <a href={accountRoute("/signin", returnTo)} className="tt-action mt-6 inline-flex items-center justify-center px-5">Sign in →</a> : <p role="status" className="mt-6 font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)]">Finishing account setup…</p>}
  </AccountShell>;
}
