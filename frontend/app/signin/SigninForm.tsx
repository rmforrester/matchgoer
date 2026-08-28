"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import AccountShell from "@/app/components/AccountShell";
import { accountRoute, completeAuthenticatedFlow, safeReturnTo, userFacingAuthError } from "@/lib/auth-flow";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { clearConversionHandoffAfter, loadConversionHandoff, prepareConversionHandoff } from "@/lib/account-conversion-checkpoint";

export default function SigninForm({ returnTo: requestedReturnTo, handoffToken, convertAnonymous = false }: { returnTo?: string; handoffToken?: string; convertAnonymous?: boolean }) {
  const router = useRouter();
  const returnTo = safeReturnTo(requestedReturnTo);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const supabase = getSupabaseBrowserClient();
    if (!supabase) return setError("Account services are unavailable right now.");
    setSaving(true); setError("");
    try {
      let checkpoint = loadConversionHandoff();
      if (convertAnonymous && !handoffToken && !checkpoint) {
        checkpoint = await prepareConversionHandoff(returnTo);
      }
      const { data, error: signinError } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
      if (signinError) throw signinError;
      if (!data.session) throw new Error("No provider session was created");
      checkpoint = loadConversionHandoff() ?? checkpoint;
      const destination = await clearConversionHandoffAfter(
        completeAuthenticatedFlow(data.session, checkpoint?.returnTo ?? returnTo, handoffToken ?? checkpoint?.token),
      );
      router.replace(destination.route);
      router.refresh();
    } catch (requestError) {
      setError(userFacingAuthError(requestError, "We couldn't sign you in. Try again."));
    } finally { setSaving(false); }
  }

  return <AccountShell kicker="Account access" title="Sign in" intro="Pick up your matchdays, grounds and Matchgoer profile.">
    <form onSubmit={submit} className="mt-6 grid gap-4">
      <label className="grid gap-1 text-sm font-extrabold uppercase tracking-[0.06em]">Email<input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} className="tt-control px-3 font-normal normal-case tracking-normal" /></label>
      <label className="grid gap-1 text-sm font-extrabold uppercase tracking-[0.06em]">Password<input required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} className="tt-control px-3 font-normal normal-case tracking-normal" /></label>
      {error && <p role="alert" className="text-sm font-bold text-red-800">{error}</p>}
      <button disabled={saving} className="tt-action px-5">{saving ? "Signing in…" : "Sign in"}</button>
    </form>
    <p className="mt-6 border-t border-[var(--tt-rule)] pt-4 text-sm">New to Matchgoer? <Link className="font-extrabold uppercase text-[var(--tt-blue)] underline decoration-2 underline-offset-4" href={accountRoute("/signup", returnTo)}>Create account →</Link></p>
  </AccountShell>;
}
