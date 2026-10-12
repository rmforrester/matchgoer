"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import AccountShell from "@/app/components/AccountShell";
import { useAuth } from "@/app/components/AuthProvider";
import api from "@/lib/api";
import { safeReturnTo, signinRoute, userFacingAuthError } from "@/lib/auth-flow";

// Compatibility destination for old links or accounts missing a profile.
// Provision through the existing API; no required setup form.
export default function ProfileOnboarding({ returnTo: requestedReturnTo }: { returnTo?: string }) {
  const router = useRouter();
  const { loading, authenticated, refreshAccount } = useAuth();
  const returnTo = safeReturnTo(requestedReturnTo);
  const [error, setError] = useState("");

  useEffect(() => {
    if (loading) return;
    if (!authenticated) {
      router.replace(signinRoute(returnTo));
      return;
    }
    let cancelled = false;
    void api.patch("/profile", {}).then(async () => {
      await refreshAccount();
      if (!cancelled) router.replace(returnTo);
    }).catch((requestError) => {
      if (!cancelled) setError(userFacingAuthError(requestError, "We couldn't finish account setup. Please try signing in again."));
    });
    return () => { cancelled = true; };
  }, [authenticated, loading, refreshAccount, returnTo, router]);

  return <AccountShell kicker="Your account" title={error ? "Setup paused" : "Getting your account ready"} intro={error || "Your football history stays with you. No profile setup is required."}>
    {error ? <><p role="alert" className="mt-4 text-sm font-bold text-red-800">{error}</p><Link href={signinRoute(returnTo)} className="tt-action mt-6 inline-flex items-center justify-center px-5">Sign in</Link></> : <p role="status" className="mt-6">Continuing to Matchgoer…</p>}
  </AccountShell>;
}
