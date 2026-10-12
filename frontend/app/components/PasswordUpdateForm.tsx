"use client";
import { FormEvent, useState } from "react";
import Link from "next/link";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { updatePassword } from "@/lib/auth-reliability";
import { userFacingAuthError } from "@/lib/auth-flow";

export default function PasswordUpdateForm({ onSuccess }: { onSuccess?: () => void }) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(""); setSaved(false);
    if (password.length < 8) return setError("Use at least 8 characters.");
    if (password !== confirmation) return setError("The passwords do not match.");
    const client = getSupabaseBrowserClient();
    if (!client) return setError("Account services are unavailable right now.");
    setBusy(true);
    try { await updatePassword(client, password); setPassword(""); setConfirmation(""); setSaved(true); onSuccess?.(); }
    catch (requestError) { setError(userFacingAuthError(requestError, "We couldn't change your password. Try again or request a fresh reset link.")); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="mt-4 grid gap-3">
    <label className="grid gap-1 text-sm font-bold">New password<input required minLength={8} type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} className="tt-control w-full min-w-0 px-3 font-normal" /><span className="font-normal text-[var(--tt-muted)]">At least 8 characters.</span></label>
    <label className="grid gap-1 text-sm font-bold">Confirm new password<input required minLength={8} type="password" autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} className="tt-control w-full min-w-0 px-3 font-normal" /></label>
    {error && <p role="alert" className="text-sm font-bold text-red-800">{error}</p>}
    {saved && <p role="status" className="text-sm font-bold text-[var(--brand-interactive)]">Password changed.</p>}
    <button disabled={busy} className="tt-action px-4">{busy ? "Saving…" : "Save password"}</button>
    <Link href="/auth/forgot-password?returnTo=%2Faccount" className="min-h-11 content-center text-sm underline">Request a password-reset link</Link>
  </form>;
}
