import axios from "axios";
import type { Session } from "@supabase/supabase-js";

import api from "./api";

export type AuthDestination = {
  route: string;
  kind: "ready" | "onboarding" | "conflict";
};

export function safeReturnTo(value: string | null | undefined, fallback = "/my-football?tab=interested") {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return fallback;
  try {
    const parsed = new URL(value, "http://terrace-talk.local");
    if (parsed.origin !== "http://terrace-talk.local") return fallback;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallback;
  }
}

export function accountRoute(path: string, returnTo?: string | null) {
  const safe = safeReturnTo(returnTo);
  return `${path}?returnTo=${encodeURIComponent(safe)}`;
}

function errorCode(error: unknown) {
  if (!axios.isAxiosError(error)) return null;
  const detail = error.response?.data?.detail;
  return detail && typeof detail === "object" && "code" in detail ? String(detail.code) : null;
}

async function registeredDestination(returnTo: string): Promise<AuthDestination> {
  const context = await api.get("/account/context");
  if (context.data.anonymous_activity) {
    return { kind: "conflict", route: accountRoute("/account/conflict", returnTo) };
  }
  if (!context.data.profile_complete) {
    return { kind: "onboarding", route: accountRoute("/account/onboarding", returnTo) };
  }
  return { kind: "ready", route: returnTo };
}

export async function completeAuthenticatedFlow(
  session: Session,
  requestedReturnTo?: string | null,
  handoffToken?: string | null,
): Promise<AuthDestination> {
  const returnTo = safeReturnTo(requestedReturnTo);
  const authorization = { Authorization: `Bearer ${session.access_token}` };
  try {
    const current = await api.get("/session", { headers: authorization });
    if (current.data.anonymous === false) return registeredDestination(returnTo);
  } catch (error) {
    if (errorCode(error) !== "IDENTITY_NOT_LINKED") throw error;
  }

  try {
    const claim = await api.post("/account/claim", { handoff_token: handoffToken || null }, { headers: authorization });
    if (!claim.data.profile_complete) {
      return { kind: "onboarding", route: accountRoute("/account/onboarding", returnTo) };
    }
    return { kind: "ready", route: accountRoute("/account/ready", returnTo) };
  } catch (error) {
    const code = errorCode(error);
    if (code === "IDENTITY_ALREADY_LINKED" || code === "ACCOUNT_ALREADY_REGISTERED") {
      return { kind: "conflict", route: accountRoute("/account/conflict", returnTo) };
    }
    throw error;
  }
}

export function userFacingAuthError(error: unknown, fallback: string) {
  const providerMessage = error instanceof Error ? error.message.toLowerCase() : "";
  if (providerMessage.includes("invalid login credentials")) return "The email or password is incorrect.";
  if (providerMessage.includes("email not confirmed")) return "Confirm your email before signing in.";
  if (providerMessage.includes("already registered") || providerMessage.includes("user already registered")) return "An account already exists for this email. Sign in instead.";
  if (!axios.isAxiosError(error)) return fallback;
  const code = errorCode(error);
  if (code === "TOKEN_EXPIRED") return "Your session has expired. Sign in again.";
  if (code === "IDENTITY_NOT_LINKED") return "This account is not connected to Terrace Talk yet.";
  if (code === "ANONYMOUS_SESSION_REQUIRED" || code === "ANONYMOUS_SESSION_INVALID" || code === "ACCOUNT_HANDOFF_INVALID" || code === "ACCOUNT_HANDOFF_EXPIRED" || code === "ACCOUNT_HANDOFF_USED" || code === "ACCOUNT_HANDOFF_SESSION_MISMATCH" || code === "ACCOUNT_HANDOFF_OWNER_MISMATCH") return "We couldn't verify the matchdays saved before signup. Your account was not switched to another supporter. Return to the original browser and try again.";
  return fallback;
}
