"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import api from "@/lib/api";
import { getSupabaseBrowserClient } from "@/lib/supabase";

type AccountProfile = {
  username: string | null;
  display_name: string;
  profile_complete: boolean;
};

type AuthContextValue = {
  loading: boolean;
  authenticated: boolean;
  profile: AccountProfile | null;
  refreshAccount: () => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [registered, setRegistered] = useState(false);
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [loading, setLoading] = useState(Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  ));

  const refreshAccount = useCallback(async () => {
    const supabase = getSupabaseBrowserClient();
    const current = await supabase?.auth.getSession();
    const providerSession = current?.data.session ?? null;
    setSession(providerSession);
    if (!providerSession) {
      setRegistered(false);
      setProfile(null);
      return;
    }
    try {
      const identity = await api.get<{ anonymous: boolean }>("/session");
      if (identity.data.anonymous !== false) throw new Error("Provider session is not registered");
      setRegistered(true);
      const response = await api.get<AccountProfile | null>("/profile");
      setProfile(response.data);
    } catch {
      setRegistered(false);
      setProfile(null);
    }
  }, []);

  useEffect(() => {
    const supabase = getSupabaseBrowserClient();
    if (!supabase) {
      return;
    }
    const initialization = window.setTimeout(() => {
      void refreshAccount().finally(() => setLoading(false));
    }, 0);
    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      if (!nextSession) {
        setRegistered(false);
        setProfile(null);
      }
      window.setTimeout(() => void refreshAccount(), 0);
    });
    return () => {
      window.clearTimeout(initialization);
      data.subscription.unsubscribe();
    };
  }, [refreshAccount]);

  const signOut = useCallback(async () => {
    const supabase = getSupabaseBrowserClient();
    await supabase?.auth.signOut();
    setSession(null);
    setRegistered(false);
    setProfile(null);
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    loading,
    authenticated: Boolean(session && registered),
    profile,
    refreshAccount,
    signOut,
  }), [loading, profile, refreshAccount, registered, session, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
