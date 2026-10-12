"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import AccountShell from "@/app/components/AccountShell";
import { accountRoute, authCallbackRoute, safeReturnTo, userFacingAuthError } from "@/lib/auth-flow";
import { prepareConversionHandoff, savePendingWhosGoingFromReturnTo } from "@/lib/account-conversion-checkpoint";
import { emailRateLimited } from "@/lib/auth-reliability";
import { useEmailCooldown } from "@/lib/use-email-cooldown";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { registrationStarted } from "@/lib/analytics";

export default function SignupForm({ returnTo: requestedReturnTo }: { returnTo?: string }) {
  const returnTo = safeReturnTo(requestedReturnTo);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmationPending, setConfirmationPending] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const cooldown = useEmailCooldown("signup");

  const redirectUrl = (handoffToken: string) => `${window.location.origin}${authCallbackRoute(returnTo, handoffToken)}`;

  async function prepareConversion() {
    const handoff = await prepareConversionHandoff(returnTo);
    savePendingWhosGoingFromReturnTo(returnTo);
    return handoff.token;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (saving || cooldown.remaining) return;
    const supabase = getSupabaseBrowserClient();
    if (!supabase) return setError("Account services are unavailable right now.");
    setSaving(true); setError(""); setMessage("");
    try {
      const handoffToken = await prepareConversion();
      const { data, error: signupError } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: { emailRedirectTo: redirectUrl(handoffToken) },
      });
      if (signupError) throw signupError;
      if (data.session) {
        setError("Email confirmation is not enabled as expected. Account setup has paused safely.");
        return;
      }
      setConfirmationPending(true);
      cooldown.start();
      if (data.user?.identities?.length) registrationStarted();
    } catch (requestError) {
      if (emailRateLimited(requestError)) cooldown.start();
      setError(userFacingAuthError(requestError, "We couldn't create your account. Try again."));
    } finally { setSaving(false); }
  }

  async function resend() {
    if (saving || cooldown.remaining) return;
    const supabase = getSupabaseBrowserClient();
    if (!supabase || !email.trim()) return;
    setSaving(true); setError(""); setMessage("");
    try {
      const handoffToken = await prepareConversion();
      const { error: resendError } = await supabase.auth.resend({ type: "signup", email: email.trim(), options: { emailRedirectTo: redirectUrl(handoffToken) } });
      if (resendError) throw resendError;
      setMessage("Confirmation email requested. Check your inbox and spam folder.");
      cooldown.start();
    } catch (requestError) {
      if (emailRateLimited(requestError)) cooldown.start();
      setError(userFacingAuthError(requestError, "We couldn't resend the confirmation email."));
    }
    setSaving(false);
  }

  if (confirmationPending) return <AccountShell kicker="Account setup" title="Check your email" intro="If this email needs confirmation, a link will be sent. If you already confirmed your email, sign in instead.">
    <p className="mt-5 text-sm font-semibold">Use the same browser so your matchdays and grounds can stay with you.</p>
    {message && <p role="status" className="mt-4 border-l-4 border-[var(--brand-interactive)] pl-3 font-semibold">{message}</p>}
    {error && <p role="alert" className="mt-4 text-sm font-bold text-red-800">{error}</p>}
    <div className="mt-6 grid gap-3"><button type="button" disabled={saving || cooldown.remaining > 0} onClick={() => void resend()} className="tt-action px-4">{saving ? "Sending…" : cooldown.remaining ? `Resend in ${cooldown.remaining}s` : "Resend email"}</button><Link href={accountRoute("/signin", returnTo)} className="tt-action tt-action-secondary inline-flex items-center justify-center px-4">Sign in →</Link></div>
  </AccountShell>;

  return <AccountShell kicker="Account setup" title="Create your account" intro="Keep your matchdays, grounds and football history with you.">
    <form onSubmit={submit} className="mt-6 grid gap-4">
      <label className="grid gap-1 text-sm font-extrabold uppercase tracking-[0.06em]">Email<input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} className="tt-control px-3 font-normal normal-case tracking-normal" /></label>
      <label className="grid gap-1 text-sm font-extrabold uppercase tracking-[0.06em]">Password<input required type="password" minLength={8} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} className="tt-control px-3 font-normal normal-case tracking-normal" /><span className="font-normal normal-case tracking-normal text-[var(--tt-muted)]">At least 8 characters.</span></label>
      {error && <p role="alert" className="text-sm font-bold text-red-800">{error}</p>}
      <button disabled={saving || cooldown.remaining > 0} className="tt-action px-5">{saving ? "Creating…" : cooldown.remaining ? `Try again in ${cooldown.remaining}s` : "Create account"}</button>
    </form>
    <p className="mt-6 border-t border-[var(--tt-rule)] pt-4 text-sm">Already have an account? <Link className="font-extrabold uppercase text-[var(--brand-interactive)] underline decoration-2 underline-offset-4" href={accountRoute("/signin", returnTo)}>Sign in →</Link></p>
  </AccountShell>;
}
