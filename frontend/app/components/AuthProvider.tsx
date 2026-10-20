"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import api from "@/lib/api";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { accountIssue, logout, rememberedRecovery, rememberRecovery, type AccountIssue } from "@/lib/auth-reliability";
import { setAnalyticsAudience, type AudienceClass } from "@/lib/analytics";

type AccountProfile = {
  username: string | null;
  display_name: string;
  profile_complete: boolean;
};

type AuthContextValue = {
  audienceClass: AudienceClass | null;
  loading: boolean;
  authenticated: boolean;
  accountKey: string;
  profile: AccountProfile | null;
  email: string | null;
  issue: AccountIssue | null;
  logoutError: string | null;
  passwordRecovery: boolean;
  finishPasswordRecovery: () => void;
  isPasswordRecovery: () => boolean;
  refreshAccount: () => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [audienceClass, setAudienceClass] = useState<AudienceClass | null>(null);
  const applyAudience = useCallback((value: AudienceClass | null) => {
    setAnalyticsAudience(value);
    setAudienceClass(value);
  }, []);
  const [session, setSession] = useState<Session | null>(null);
  const [registered, setRegistered] = useState(false);
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [issue, setIssue] = useState<AccountIssue | null>(null);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [passwordRecovery, setPasswordRecovery] = useState(false);
  const owner = useRef<string | null>(null);
  const refreshGeneration = useRef(0);
  const loggingOut = useRef(false);
  const recovery = useRef(false);
  const finishPasswordRecovery = useCallback(() => { recovery.current = false; setPasswordRecovery(false); rememberRecovery(null); }, []);
  const isPasswordRecovery = useCallback(() => recovery.current, []);
  const [loading, setLoading] = useState(Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  ));

  const refreshAccount = useCallback(async () => {
    const generation = ++refreshGeneration.current;
    applyAudience(null);
    const supabase = getSupabaseBrowserClient();
    let current;
    try {
      current = await supabase?.auth.getSession();
      if (current?.error) throw current.error;
    } catch (error) {
      if (generation !== refreshGeneration.current) return;
      const nextIssue = accountIssue(error);
      setIssue(nextIssue);
      if (nextIssue === "expired") { setSession(null); setRegistered(false); setProfile(null); owner.current = null; finishPasswordRecovery(); }
      return;
    }
    const providerSession = current?.data.session ?? null;
    if (generation !== refreshGeneration.current) return;
    if (owner.current !== (providerSession?.user.id ?? null)) {
      setRegistered(false); setProfile(null);
    }
    owner.current = providerSession?.user.id ?? null;
    setSession(providerSession);
    if (!providerSession) {
      applyAudience("unclassified");
      setRegistered(false);
      setProfile(null);
      finishPasswordRecovery();
      return;
    }
    try {
      const headers = { Authorization: `Bearer ${providerSession.access_token}` };
      const identity = await api.get<{ anonymous: boolean; audience_class?: unknown }>("/session", { headers });
      if (generation !== refreshGeneration.current || owner.current !== providerSession.user.id) return;
      if (identity.data.anonymous !== false) {
        setRegistered(false); setProfile(null); setIssue("unlinked"); return;
      }
      const response = await api.get<AccountProfile | null>("/profile", { headers });
      if (generation !== refreshGeneration.current || owner.current !== providerSession.user.id) return;
      setRegistered(true);
      setProfile(response.data);
      setIssue(null);
      const classification = identity.data.audience_class;
      applyAudience(classification === "internal" || classification === "external" ? classification : null);
    } catch (error) {
      if (generation !== refreshGeneration.current || owner.current !== providerSession.user.id) return;
      const nextIssue = accountIssue(error);
      setIssue(nextIssue);
      if (nextIssue !== "unavailable") { setRegistered(false); setProfile(null); }
    }
  }, [applyAudience, finishPasswordRecovery]);

  useEffect(() => {
    const supabase = getSupabaseBrowserClient();
    if (!supabase) {
      const timer = window.setTimeout(() => void refreshAccount().finally(() => setLoading(false)), 0);
      return () => window.clearTimeout(timer);
    }
    const initialization = window.setTimeout(() => {
      void refreshAccount().finally(() => setLoading(false));
    }, 0);
    const { data } = supabase.auth.onAuthStateChange((event, nextSession) => {
      refreshGeneration.current += 1;
      applyAudience(null);
      if (event === "PASSWORD_RECOVERY" && nextSession) { recovery.current = true; setPasswordRecovery(true); rememberRecovery(nextSession.user.id); }
      else if (event === "SIGNED_IN" && nextSession) {
        recovery.current = rememberedRecovery(nextSession.user.id);
        setPasswordRecovery(recovery.current);
        if (!recovery.current) rememberRecovery(null);
        setLogoutError(null);
      }
      else if (event === "INITIAL_SESSION" && nextSession) { recovery.current = rememberedRecovery(nextSession.user.id); setPasswordRecovery(recovery.current); }
      if (nextSession && owner.current !== nextSession.user.id) { setRegistered(false); setProfile(null); }
      setSession(nextSession);
      if (!nextSession) {
        setRegistered(false);
        setProfile(null);
        setPasswordRecovery(false);
        recovery.current = false;
        rememberRecovery(null);
        if (event === "SIGNED_OUT") {
          setIssue(!loggingOut.current && owner.current ? "expired" : null);
          owner.current = null;
        }
      }
      window.setTimeout(() => void refreshAccount(), 0);
    });
    return () => {
      window.clearTimeout(initialization);
      data.subscription.unsubscribe();
      setAnalyticsAudience(null);
    };
  }, [applyAudience, finishPasswordRecovery, refreshAccount]);

  const signOut = useCallback(async () => {
    refreshGeneration.current += 1;
    applyAudience(null);
    const supabase = getSupabaseBrowserClient();
    setLogoutError(null);
    loggingOut.current = true;
    try { await logout(supabase); }
    catch (error) {
      let cleared = false;
      try { const current = await supabase?.auth.getSession(); cleared = Boolean(supabase && !current?.error && !current?.data.session); } catch { /* State cannot be confirmed. */ }
      setLogoutError(cleared ? "You're signed out on this device, but we couldn't confirm sign-out of other sessions. Sign in again if you need to retry." : "We couldn't confirm logout. Please try again.");
      void refreshAccount();
      throw error;
    } finally { loggingOut.current = false; }
    setSession(null);
    setRegistered(false);
    setProfile(null);
    setIssue(null);
    setPasswordRecovery(false);
    recovery.current = false;
    rememberRecovery(null);
    owner.current = null;
    void refreshAccount();
  }, [applyAudience, refreshAccount]);

  const value = useMemo<AuthContextValue>(() => ({
    audienceClass,
    loading,
    authenticated: Boolean(session && registered),
    accountKey: session?.user.id ?? "guest",
    profile,
    email: session?.user.email ?? null,
    issue,
    logoutError,
    passwordRecovery,
    finishPasswordRecovery,
    isPasswordRecovery,
    refreshAccount,
    signOut,
  }), [audienceClass, finishPasswordRecovery, isPasswordRecovery, issue, loading, logoutError, passwordRecovery, profile, refreshAccount, registered, session, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
