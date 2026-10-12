"use client";
import Link from "next/link";
import { FormEvent, useState } from "react";
import AccountShell from "./AccountShell";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { accountRoute, authCallbackRoute, safeReturnTo, userFacingAuthError } from "@/lib/auth-flow";
import { prepareConversionHandoff } from "@/lib/account-conversion-checkpoint";
import { emailRateLimited, requestPasswordRecovery } from "@/lib/auth-reliability";
import { useEmailCooldown } from "@/lib/use-email-cooldown";

export default function AuthEmailForm({ kind, returnTo: requested }: { kind: "signup" | "recovery"; returnTo?: string }) {
  const returnTo = safeReturnTo(requested, "/account");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const cooldown = useEmailCooldown(kind);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy || cooldown.remaining) return;
    const client = getSupabaseBrowserClient();
    if (!client) return setError("Account services are unavailable right now.");
    setBusy(true); setError(""); setSent(false);
    try {
      if (kind === "recovery") await requestPasswordRecovery(client, email, window.location.origin, returnTo);
      else {
        const handoff = await prepareConversionHandoff(returnTo);
        const { error } = await client.auth.resend({ type: "signup", email: email.trim(), options: { emailRedirectTo: `${window.location.origin}${authCallbackRoute(returnTo, handoff.token)}` } });
        if (error) throw error;
      }
      setSent(true); cooldown.start();
    } catch (requestError) {
      if (emailRateLimited(requestError)) cooldown.start();
      setError(userFacingAuthError(requestError, "We couldn't request the email. Please try again."));
    } finally { setBusy(false); }
  }
  return <AccountShell kicker="Account access" title={kind === "recovery" ? "Reset your password" : "Confirm your email"} intro={kind === "recovery" ? "Request a link to choose a new password." : "Request a fresh confirmation link. Use your original browser to preserve the history saved before signup."}>
    <form onSubmit={submit} className="mt-5 grid gap-3"><label className="grid gap-1 text-sm font-bold">Email<input required type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} className="tt-control w-full min-w-0 px-3 font-normal" /></label>
      {error && <p role="alert" className="text-sm font-bold text-red-800">{error}</p>}
      {sent && <p role="status" className="text-sm font-semibold">{kind === "recovery" ? "If an account uses this email, a password-reset link will be sent. Check your inbox and spam folder." : "If this email needs confirmation, a new link will be sent. If you already confirmed it, sign in instead."}</p>}
      <button disabled={busy || cooldown.remaining > 0} className="tt-action px-4">{busy ? "Requesting…" : cooldown.remaining ? `Try again in ${cooldown.remaining}s` : kind === "recovery" ? "Send reset link" : "Send confirmation link"}</button>
    </form><Link href={accountRoute("/signin", returnTo)} className="mt-4 block min-h-11 content-center text-sm font-bold underline">Back to sign in</Link>
  </AccountShell>;
}
