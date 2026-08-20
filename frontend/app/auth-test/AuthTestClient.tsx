"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Session } from "@supabase/supabase-js";

import api from "@/lib/api";
import { getSupabaseBrowserClient } from "@/lib/supabase";

type TerraceSession = {
  user_id: number;
  anonymous: boolean;
};

type ClaimResult = {
  user_id: number;
  account_status: string;
  claimed: boolean;
  idempotent: boolean;
  profile_complete: boolean;
};

type ProbeResult = {
  endpoint: string;
  status: number | "error";
};

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabasePublishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

function safeError(error: unknown) {
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { status?: number; data?: { detail?: unknown } } }).response;
    const detail = response?.data?.detail;
    if (detail && typeof detail === "object" && "code" in detail) {
      return `${response?.status ?? "Request failed"}: ${String(detail.code)}`;
    }
    return `${response?.status ?? "Request failed"}`;
  }
  return error instanceof Error ? error.message : "Request failed";
}

export default function AuthTestClient() {
  const supabase = getSupabaseBrowserClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [providerSession, setProviderSession] = useState<Session | null>(null);
  const [terraceSession, setTerraceSession] = useState<TerraceSession | null>(null);
  const [claimResult, setClaimResult] = useState<ClaimResult | null>(null);
  const [fixtureId, setFixtureId] = useState("");
  const [probes, setProbes] = useState<ProbeResult[]>([]);
  const [bearerOwnerId, setBearerOwnerId] = useState<number | null>(null);
  const [status, setStatus] = useState(
    supabaseUrl && supabasePublishableKey
      ? "Establishing an isolated Terrace Talk session…"
      : "Supabase public configuration is missing.",
  );
  const [busy, setBusy] = useState(false);

  const establishTerraceSession = useCallback(async () => {
    const response = await api.get<TerraceSession>("/session");
    setTerraceSession(response.data);
    return response.data;
  }, []);

  useEffect(() => {
    if (!supabase) {
      return;
    }

    const initialization = window.setTimeout(() => {
      void establishTerraceSession()
        .then(() => setStatus("Development harness ready."))
        .catch((error) => setStatus(`Terrace Talk session failed: ${safeError(error)}`));
      void supabase.auth.getSession().then(({ data }) => setProviderSession(data.session));
    }, 0);
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setProviderSession(session);
    });
    return () => {
      window.clearTimeout(initialization);
      data.subscription.unsubscribe();
    };
  }, [establishTerraceSession, supabase]);

  async function signUp(event: FormEvent) {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setClaimResult(null);
    try {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: `${window.location.origin}/auth-test` },
      });
      if (error) throw error;
      setStatus(
        data.session
          ? "Signup returned a session. Confirm the project's email-confirmation policy before claiming."
          : "Confirmation email sent. Confirm it, return here, then sign in.",
      );
    } catch (error) {
      setStatus(`Signup failed: ${safeError(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function signIn() {
    if (!supabase) return;
    setBusy(true);
    try {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
      setStatus("Verified provider session available. Claim is ready when anonymous activity is prepared.");
    } catch (error) {
      setStatus(`Sign in failed: ${safeError(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    if (!supabase) return;
    setBusy(true);
    try {
      await supabase.auth.signOut();
      setClaimResult(null);
      setProbes([]);
      setBearerOwnerId(null);
      setStatus("Signed out of the development provider session.");
    } finally {
      setBusy(false);
    }
  }

  async function claim() {
    if (!providerSession) return;
    setBusy(true);
    try {
      const response = await api.post<ClaimResult>(
        "/account/claim",
        {},
        { headers: { Authorization: `Bearer ${providerSession.access_token}` } },
      );
      setClaimResult(response.data);
      setTerraceSession({ user_id: response.data.user_id, anonymous: false });
      setStatus("Claim succeeded. The anonymous cookie was expired by FastAPI.");
    } catch (error) {
      setStatus(`Claim failed: ${safeError(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function runBearerProbes() {
    if (!providerSession) return;
    setBusy(true);
    const endpoints = ["/my-grounds", "/interested", "/profile"];
    if (fixtureId.trim()) endpoints.push(`/fixtures/${fixtureId.trim()}/social`);
    const headers = { Authorization: `Bearer ${providerSession.access_token}` };
    const results: ProbeResult[] = [];
    try {
      const owner = await api.get<TerraceSession>("/session", { headers });
      setBearerOwnerId(owner.data.user_id);
    } catch {
      setBearerOwnerId(null);
    }
    for (const endpoint of endpoints) {
      try {
        const response = await api.get(endpoint, { headers });
        results.push({ endpoint, status: response.status });
      } catch (error) {
        const response = (error as { response?: { status?: number } }).response;
        results.push({ endpoint, status: response?.status ?? "error" });
      }
    }
    setProbes(results);
    setStatus("Bearer probes completed; only endpoint/status metadata is shown.");
    setBusy(false);
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-10 sm:px-6">
      <p className="text-sm font-bold uppercase tracking-widest text-blue-700">Development only</p>
      <h1 className="mt-2 text-3xl font-black uppercase">Supabase claim harness</h1>
      <p className="mt-3 text-sm text-neutral-700">
        Use an incognito window and disposable credentials. Tokens, provider subjects and private user data are never displayed.
      </p>

      <section className="mt-8 border-2 border-neutral-900 p-4">
        <h2 className="font-black uppercase">Current state</h2>
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt>Terrace Talk</dt>
          <dd>{terraceSession ? `user ${terraceSession.user_id} · ${terraceSession.anonymous ? "anonymous" : "registered"}` : "not established"}</dd>
          <dt>Supabase</dt>
          <dd>{providerSession ? "authenticated session present" : "signed out"}</dd>
          <dt>Claim</dt>
          <dd>{claimResult ? `${claimResult.account_status} · ${claimResult.idempotent ? "idempotent retry" : "new claim"}` : "not completed"}</dd>
        </dl>
        <p role="status" className="mt-4 border-t pt-3 text-sm font-semibold">{status}</p>
      </section>

      <form onSubmit={signUp} className="mt-6 grid gap-4 border-2 border-neutral-900 p-4">
        <h2 className="font-black uppercase">Disposable email identity</h2>
        <label className="grid gap-1 text-sm font-bold">
          Email
          <input className="min-h-11 border border-neutral-700 px-3 font-normal" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label className="grid gap-1 text-sm font-bold">
          Password
          <input className="min-h-11 border border-neutral-700 px-3 font-normal" type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        <div className="flex flex-wrap gap-3">
          <button disabled={busy} className="min-h-11 border-2 border-neutral-900 bg-blue-700 px-4 font-black uppercase text-white disabled:opacity-50" type="submit">Sign up</button>
          <button disabled={busy} className="min-h-11 border-2 border-neutral-900 px-4 font-black uppercase disabled:opacity-50" type="button" onClick={signIn}>Sign in</button>
          <button disabled={busy || !providerSession} className="min-h-11 border-2 border-neutral-900 px-4 font-black uppercase disabled:opacity-50" type="button" onClick={signOut}>Sign out</button>
        </div>
      </form>

      <section className="mt-6 border-2 border-neutral-900 p-4">
        <h2 className="font-black uppercase">Claim and verify</h2>
        <p className="mt-2 text-sm">Before claiming, use this same incognito browser to add representative anonymous activity through Terrace Talk.</p>
        <button disabled={busy || !providerSession} className="mt-4 min-h-11 border-2 border-neutral-900 bg-blue-700 px-4 font-black uppercase text-white disabled:opacity-50" type="button" onClick={claim}>Claim anonymous user</button>
        <label className="mt-5 grid gap-1 text-sm font-bold">
          Fixture ID for optional social-state probe
          <input className="min-h-11 border border-neutral-700 px-3 font-normal" inputMode="numeric" value={fixtureId} onChange={(event) => setFixtureId(event.target.value)} />
        </label>
        <button disabled={busy || !providerSession} className="mt-3 min-h-11 border-2 border-neutral-900 px-4 font-black uppercase disabled:opacity-50" type="button" onClick={runBearerProbes}>Run bearer probes</button>
        {probes.length > 0 && <ul className="mt-4 text-sm">{probes.map((probe) => <li key={probe.endpoint}>{probe.endpoint}: HTTP {probe.status}</li>)}</ul>}
        {bearerOwnerId !== null && <p className="mt-3 text-sm font-bold">Bearer resolved Terrace Talk user: {bearerOwnerId}</p>}
      </section>
    </main>
  );
}
