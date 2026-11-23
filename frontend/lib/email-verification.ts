import type { SupabaseClient } from "@supabase/supabase-js";
import { authCallbackRoute, safeReturnTo, signinRoute } from "./auth-flow.ts";

export const VERIFICATION_PAGE = "https://beta.matchgoer.com/auth/verified";
export const MATCHGOER_DOWNLOAD = "https://apps.apple.com/app/id6828049651";
const pendingKey = "matchgoer.native.signup-return.v1";
const callback = "com.matchgoer.app://auth/callback";
type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function signupVerificationRedirect(origin: string, returnTo: string, handoff: string,
  native = process.env.NEXT_PUBLIC_NATIVE_AUTH === "true", storage?: StorageLike, now = Date.now()) {
  if (!native) return `${origin}${authCallbackRoute(returnTo, handoff)}`;
  const target = storage ?? window.localStorage;
  target.setItem(pendingKey, JSON.stringify({ returnTo: safeReturnTo(returnTo), handoff, expires: now + 60 * 60 * 1000 }));
  // The handoff and PKCE verifier stay on the originating device, never the web page.
  return VERIFICATION_PAGE;
}

export type VerificationLanding = { kind: "continue"; code: string } | { kind: "expired" | "invalid" | "missing" };
export function verificationLanding(search: string, hash: string): VerificationLanding {
  const query = new URLSearchParams(search), fragment = new URLSearchParams(hash.replace(/^#/, ""));
  if ([query, fragment].some(p => p.has("access_token") || p.has("refresh_token"))) return { kind: "invalid" };
  const errorCode = query.get("error_code") ?? fragment.get("error_code");
  if (errorCode === "otp_expired" || errorCode === "flow_state_expired") return { kind: "expired" };
  if (errorCode || query.has("error") || fragment.has("error")) return { kind: "invalid" };
  const codes = query.getAll("code");
  if (!codes.length) return { kind: "missing" };
  return codes.length === 1 && /^[A-Za-z0-9._~-]{1,2048}$/.test(codes[0])
    ? { kind: "continue", code: codes[0] } : { kind: "invalid" };
}

export function verificationAppLink(state: VerificationLanding, action?: "signin" | "confirm") {
  const url = new URL(callback);
  url.searchParams.set("flow", "signup");
  if (state.kind === "continue" && !action) url.searchParams.set("code", state.code);
  else url.searchParams.set("action", action ?? "signin");
  return url.href;
}

export function signupReturnRoute(raw: string, storage: StorageLike, now = Date.now()): string | null {
  const url = new URL(raw);
  if (url.searchParams.get("flow") !== "signup") return null; // Existing OAuth/recovery path unchanged.
  if (url.protocol !== "com.matchgoer.app:" || url.host !== "auth" || url.pathname !== "/callback"
      || url.username || url.password || url.hash || url.port) throw new Error("Unexpected signup return");
  for (const key of url.searchParams.keys()) {
    if (!["flow", "code", "action"].includes(key) || url.searchParams.getAll(key).length !== 1) throw new Error("Unexpected signup fields");
  }
  let pending: { returnTo?: string; handoff?: string; expires?: number } | null = null;
  try { pending = JSON.parse(storage.getItem(pendingKey) ?? "null"); } catch { /* No trusted local continuity. */ }
  const current = pending && typeof pending.expires === "number" && pending.expires > now ? pending : null;
  const returnTo = current ? safeReturnTo(current.returnTo) : safeReturnTo(null);
  const handoff = current && typeof current.handoff === "string" ? current.handoff : undefined;
  const action = url.searchParams.get("action");
  if (action) {
    if (url.searchParams.has("code") || !["signin", "confirm"].includes(action)) throw new Error("Unexpected signup action");
    return action === "signin" ? signinRoute(returnTo, handoff) : `/auth/confirm?returnTo=${encodeURIComponent(returnTo)}`;
  }
  const result = verificationLanding(url.search, "");
  if (result.kind !== "continue") throw new Error("Missing signup code");
  if (!current) return signinRoute(returnTo); // Another/new device cannot exchange the original PKCE code.
  const query = new URLSearchParams({ flow: "signup", code: result.code, returnTo });
  if (handoff) query.set("handoff", handoff);
  return `/auth/callback?${query}`;
}

export async function validateSignupSession(client: SupabaseClient, code: string) {
  const exchanged = await client.auth.exchangeCodeForSession(code);
  if (exchanged.error) throw exchanged.error;
  const verified = await client.auth.getUser();
  if (verified.error) throw verified.error;
  if (!exchanged.data.session || !verified.data.user?.email_confirmed_at
      || verified.data.user.id !== exchanged.data.session.user.id) throw new Error("Email confirmation not verified");
  return exchanged.data.session;
}

export function clearSignupReturn(storage: StorageLike = window.localStorage) {
  storage.removeItem(pendingKey);
}
