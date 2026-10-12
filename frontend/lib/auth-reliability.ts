import axios from "axios";
import type { SupabaseClient } from "@supabase/supabase-js";
import { safeReturnTo } from "./auth-flow.ts";

export type AccountIssue = "expired" | "unavailable" | "unlinked";
const recoveryOwnerKey = "matchgoer.auth.recovery-owner";

// UI continuity only: password updates still require Supabase authentication.
export function rememberRecovery(owner: string | null) {
  try { if (owner) sessionStorage.setItem(recoveryOwnerKey, owner); else sessionStorage.removeItem(recoveryOwnerKey); } catch { /* Verified in-memory recovery remains usable. */ }
}
export function rememberedRecovery(owner: string) {
  try { return sessionStorage.getItem(recoveryOwnerKey) === owner; } catch { return false; }
}

export function accountIssue(error: unknown): AccountIssue {
  if (axios.isAxiosError(error)) {
    if (error.response?.data?.detail?.code === "IDENTITY_NOT_LINKED") return "unlinked";
    if (error.response?.status === 401) return "expired";
  }
  const code = (error as { code?: string } | null)?.code;
  return ["session_not_found", "refresh_token_not_found", "refresh_token_already_used"].includes(code ?? "") ? "expired" : "unavailable";
}

export function emailRateLimited(error: unknown) {
  return (error as { status?: number } | null)?.status === 429;
}

export function confirmationLinkError(error: unknown) {
  const code = (error as { code?: string } | null)?.code ?? "";
  const message = error instanceof Error ? error.message.toLowerCase() : "";
  return ["otp_expired", "flow_state_expired", "flow_state_not_found"].includes(code)
    || /expired|already.*used|invalid.*token|invalid.*link/.test(message);
}

export function recoveryRedirect(origin: string, returnTo?: string | null) {
  return `${origin}/auth/recovery?returnTo=${encodeURIComponent(safeReturnTo(returnTo, "/account"))}`;
}

// Recovery operations deliberately do not call Matchgoer's account-claim API.
export async function requestPasswordRecovery(client: SupabaseClient, email: string, origin: string, returnTo?: string | null) {
  const { error } = await client.auth.resetPasswordForEmail(email.trim(), { redirectTo: recoveryRedirect(origin, returnTo) });
  if (error) throw error;
}

export async function updatePassword(client: SupabaseClient, password: string) {
  const { error } = await client.auth.updateUser({ password });
  if (error) throw error;
}

export async function logout(client: SupabaseClient | null) {
  if (!client) throw new Error("Account services unavailable");
  const { error } = await client.auth.signOut();
  if (error) throw error;
}
