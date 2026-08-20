"use client";

import axios from "axios";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import AccountShell from "@/app/components/AccountShell";
import { useAuth } from "@/app/components/AuthProvider";
import api from "@/lib/api";
import { safeReturnTo } from "@/lib/auth-flow";

type Profile = { username?: string | null; display_name?: string; supported_club?: string | null; broad_location?: string | null; bio?: string | null };

export default function ProfileOnboarding({ returnTo: requestedReturnTo }: { returnTo?: string }) {
  const router = useRouter();
  const { refreshAccount } = useAuth();
  const returnTo = safeReturnTo(requestedReturnTo);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [supportedClub, setSupportedClub] = useState("");
  const [location, setLocation] = useState("");
  const [bio, setBio] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void api.get<Profile | null>("/profile").then(({ data }) => {
      if (!data) return;
      setUsername(data.username ?? ""); setDisplayName(data.display_name ?? ""); setSupportedClub(data.supported_club ?? ""); setLocation(data.broad_location ?? ""); setBio(data.bio ?? "");
    }).catch(() => undefined);
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const normalizedUsername = username.trim();
    if (!/^[A-Za-z0-9_]{3,30}$/.test(normalizedUsername)) return setError("Use 3 to 30 letters, numbers or underscores for your username.");
    if (displayName.trim().length < 2) return setError("Display name must be at least 2 characters.");
    setSaving(true); setError("");
    try {
      await api.patch("/profile", { username: normalizedUsername, display_name: displayName.trim(), supported_club: supportedClub.trim() || null, broad_location: location.trim() || null, bio: bio.trim() || null });
      await refreshAccount();
      router.replace(returnTo);
      router.refresh();
    } catch (requestError) {
      const detail = axios.isAxiosError(requestError) ? requestError.response?.data?.detail : null;
      setError(detail && typeof detail === "object" && "message" in detail ? String(detail.message) : "We couldn't save your profile. Try again.");
    } finally { setSaving(false); }
  }

  return <AccountShell kicker="Nearly there" title="Your Terrace Talk profile" intro="Choose how other supporters will know you. You can add the optional details now or later.">
    <form onSubmit={submit} className="mt-6 grid gap-4">
      <label className="grid gap-1 text-sm font-extrabold uppercase tracking-[0.06em]">Username *<input required maxLength={30} autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} className="tt-control px-3 font-normal normal-case tracking-normal" /><span className="font-normal normal-case tracking-normal text-[var(--tt-muted)]">3–30 letters, numbers or underscores.</span></label>
      <label className="grid gap-1 text-sm font-extrabold uppercase tracking-[0.06em]">Display name *<input required maxLength={40} autoComplete="nickname" value={displayName} onChange={(event) => setDisplayName(event.target.value)} className="tt-control px-3 font-normal normal-case tracking-normal" /></label>
      <label className="grid gap-1 text-sm font-extrabold uppercase tracking-[0.06em]">Supported club <span className="font-normal normal-case tracking-normal text-[var(--tt-muted)]">Optional</span><input maxLength={80} value={supportedClub} onChange={(event) => setSupportedClub(event.target.value)} className="tt-control px-3 font-normal normal-case tracking-normal" /></label>
      <label className="grid gap-1 text-sm font-extrabold uppercase tracking-[0.06em]">Location <span className="font-normal normal-case tracking-normal text-[var(--tt-muted)]">Optional city or region</span><input maxLength={100} autoComplete="address-level2" value={location} onChange={(event) => setLocation(event.target.value)} className="tt-control px-3 font-normal normal-case tracking-normal" /></label>
      <label className="grid gap-1 text-sm font-extrabold uppercase tracking-[0.06em]">Bio <span className="font-normal normal-case tracking-normal text-[var(--tt-muted)]">Optional</span><textarea maxLength={280} rows={4} value={bio} onChange={(event) => setBio(event.target.value)} className="tt-control p-3 font-normal normal-case tracking-normal" /></label>
      {error && <p role="alert" className="text-sm font-bold text-red-800">{error}</p>}
      <button disabled={saving} className="tt-action px-5">{saving ? "Saving…" : "Save profile"}</button>
    </form>
  </AccountShell>;
}
