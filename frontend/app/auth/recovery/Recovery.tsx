"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import AccountShell from "@/app/components/AccountShell";
import PasswordUpdateForm from "@/app/components/PasswordUpdateForm";
import { useAuth } from "@/app/components/AuthProvider";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { accountRoute, safeReturnTo } from "@/lib/auth-flow";

export default function Recovery({ returnTo: requested, providerError }: { returnTo?: string; providerError: boolean }) {
  const { passwordRecovery, finishPasswordRecovery, email } = useAuth();
  const returnTo = safeReturnTo(requested, "/account");
  const [checked, setChecked] = useState(providerError);
  const [completed, setCompleted] = useState(false);
  useEffect(() => {
    let cancelled = false;
    // The existing Supabase client validates the URL and emits PASSWORD_RECOVERY.
    // A normal stored session alone does not activate this reset form.
    const ready = () => { if (!cancelled) setChecked(true); };
    void getSupabaseBrowserClient()?.auth.getSession().then(ready, ready);
    const timer = window.setTimeout(() => setChecked(true), 3000);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, []);
  return <AccountShell kicker="Account access" title={completed ? "Password changed" : "Reset your password"} intro={completed ? "Your new password is ready to use." : "Choose a new password using your verified reset link."}>
    {completed ? <Link className="tt-action mt-5 inline-flex min-h-11 items-center justify-center px-4" href={returnTo}>Continue →</Link> : passwordRecovery && !providerError ? <><p className="mt-4 break-all text-sm">Resetting the password for {email || "your verified account"}.</p><PasswordUpdateForm onSuccess={() => { setCompleted(true); finishPasswordRecovery(); }} /></> : !checked ? <p role="status" className="mt-5">Checking your reset link…</p> : <div className="mt-5 space-y-3"><p role="alert">This reset link is unavailable. It may have expired or already been used. Request a new link, or sign in to change your password in My Account.</p><Link className="tt-action inline-flex min-h-11 items-center justify-center px-4" href={accountRoute("/auth/forgot-password", returnTo)}>Request a new reset link</Link><Link className="block min-h-11 content-center text-sm underline" href={accountRoute("/signin", returnTo)}>Sign in</Link></div>}
  </AccountShell>;
}
