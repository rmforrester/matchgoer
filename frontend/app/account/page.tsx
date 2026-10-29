"use client";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AccountShell from "@/app/components/AccountShell";
import { useAuth } from "@/app/components/AuthProvider";
import LogoutButton from "@/app/components/LogoutButton";
import { ManageSubmissionsLink } from "@/app/components/TerraceModeration";
import AnalyticsPreferences from "@/app/components/AnalyticsPreferences";
import PasswordUpdateForm from "@/app/components/PasswordUpdateForm";
import api from "@/lib/api";
import { signinRoute, userFacingAuthError } from "@/lib/auth-flow";

export default function AccountPage() {
  const router = useRouter();
  const { authenticated, loading, profile, email, issue, logoutError, refreshAccount } = useAuth();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  useEffect(() => { const timer = window.setTimeout(() => setName(profile?.display_name ?? ""), 0); return () => window.clearTimeout(timer); }, [profile?.display_name]);
  async function save(event: FormEvent) {
    event.preventDefault(); setError(""); setSaved("");
    const value = name.trim();
    if (!value && profile) { setName(profile.display_name); setSaved("Your current display name has been kept."); return; }
    if (value && (value.length < 2 || value.length > 40)) return setError("Use 2 to 40 characters for your display name.");
    setBusy(true);
    try {
      const response = await api.patch("/profile", value ? { display_name: value } : {});
      if (!response.data.display_name || (value && response.data.display_name !== value)) throw new Error("Name not confirmed");
      await refreshAccount(); setSaved("Display name saved.");
    } catch (requestError) { setError(userFacingAuthError(requestError, "We couldn't save your display name. Please try again.")); }
    finally { setBusy(false); }
  }
  const section = "border-t border-[var(--tt-rule)] py-5 first:border-t-0";
  return <AccountShell kicker="Your Matchgoer" title="My Account" intro="Your account, preferences and a way to get in touch." showBrand={process.env.NEXT_PUBLIC_NATIVE_AUTH !== "true"}>
    <section aria-labelledby="your-account" className={section}><h2 id="your-account" className="tt-display text-2xl uppercase text-[var(--brand-interactive)]">Your Account</h2>
      {issue && <div role="status" className="mt-3 text-sm"><p>{issue === "expired" ? "Your session has ended. Sign in again to continue." : issue === "unlinked" ? "Finish confirming your email and signing in to connect your account." : "Matchgoer is temporarily unavailable. Your saved history has not been discarded."}</p>{issue === "unavailable" && <button className="min-h-11 font-bold underline" type="button" onClick={() => void refreshAccount()}>Try again</button>}</div>}
      {loading ? <p role="status" className="mt-3">Checking your account…</p> : authenticated ? <>
        <p className="mt-3 break-all text-sm"><span className="font-bold">Email</span><br />{email || "Email unavailable"}</p>
        <form onSubmit={save} className="mt-4 grid gap-2"><label className="grid gap-1 text-sm font-bold">Display name<input maxLength={40} autoComplete="nickname" value={name} onChange={e => setName(e.target.value)} className="tt-control w-full min-w-0 px-3 font-normal" /><span className="font-normal text-[var(--tt-muted)]">Optional. Leave blank to keep your current name.</span></label>
          {error && <p role="alert" className="text-sm font-bold text-red-800">{error}</p>}{saved && <p role="status" className="text-sm font-bold text-[var(--brand-interactive)]">{saved}</p>}
          <button disabled={busy} className="tt-action px-4">{busy ? "Saving…" : "Save display name"}</button></form>
        <details className="mt-4 border-t border-[var(--tt-rule)] pt-2"><summary className="min-h-11 cursor-pointer list-none content-center font-bold focus-visible:outline-2 [&::-webkit-details-marker]:hidden">Change password</summary><PasswordUpdateForm /></details>
      </> : !loading && issue !== "unavailable" && <Link href={signinRoute(process.env.NEXT_PUBLIC_NATIVE_AUTH === "true" ? "/my-football?tab=interested" : "/account")} className="tt-action mt-3 inline-flex min-h-11 items-center justify-center px-4">Sign in to your account</Link>}
    </section>
    <section aria-labelledby="preferences" className={section}><h2 id="preferences" className="tt-display mb-3 text-2xl uppercase text-[var(--brand-interactive)]">Preferences</h2><AnalyticsPreferences /></section>
    <section aria-labelledby="privacy-data" className={section}><h2 id="privacy-data" className="tt-display mb-3 text-2xl uppercase text-[var(--brand-interactive)]">Privacy &amp; Data</h2>
      <Link href="/privacy" className="block min-h-11 content-center font-bold underline underline-offset-4">Privacy &amp; cookies</Link>
      <a href="mailto:privacy@matchgoer.com?subject=Matchgoer%20personal%20data%20request" className="block min-h-11 content-center font-bold underline underline-offset-4">Request your personal data</a>
      <a href="mailto:privacy@matchgoer.com?subject=Matchgoer%20account%20deletion%20request" className="block min-h-11 content-center font-bold underline underline-offset-4">Request account deletion</a>
      <p className="mt-2 text-sm text-[var(--tt-muted)]">These open an email request to privacy@matchgoer.com. Nothing is exported or deleted immediately.</p>
    </section>
    <section aria-labelledby="help-feedback" className={section}><h2 id="help-feedback" className="tt-display mb-3 text-2xl uppercase text-[var(--brand-interactive)]">Help &amp; Feedback</h2><a href="mailto:hello@matchgoer.com?subject=Matchgoer%20feedback%20or%20problem" className="block min-h-11 content-center font-bold underline underline-offset-4">Send feedback or report a problem</a><p className="mt-2 text-sm text-[var(--tt-muted)]">Email hello@matchgoer.com.</p><ManageSubmissionsLink /></section>
    {(authenticated || logoutError) && <div role="region" aria-label="Log out" className={`${section} text-left`}>
      {authenticated && <LogoutButton className="block min-h-11 w-full text-left font-bold underline underline-offset-4 focus-visible:outline-2" onSuccess={() => router.replace("/")} />}
      {logoutError && <p role="alert" className="mt-3 text-sm text-red-800">{logoutError}</p>}
    </div>}
  </AccountShell>;
}
