import type { SupabaseClient } from "@supabase/supabase-js";
import { authCallbackRoute, safeReturnTo } from "./auth-flow.ts";
import { prepareSigninConversion, savePendingWhosGoingFromReturnTo } from "./account-conversion-checkpoint.ts";

// Build-time opt-in only, after provider setup and separate live acceptance.
export function googleSigninEnabled() {
  return process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED === "true";
}

export function googleCallbackError(error?: string | null) {
  return error === "access_denied"
    ? "Google sign-in was cancelled. You can try again or use email and password. Your saved history remains unchanged."
    : "We couldn't finish Google sign-in. Try again or use email and password. Your saved history remains unchanged.";
}

export async function beginGoogleSignin(
  client: SupabaseClient,
  origin: string,
  requestedReturnTo?: string,
  handoffToken?: string,
  convertAnonymous = false,
) {
  if (!googleSigninEnabled()) throw new Error("Google sign-in is not available yet. Use email and password.");
  const returnTo = safeReturnTo(requestedReturnTo);
  // Use the same cookie-bound, server-verified handoff as password sign-in.
  // Never infer an account owner from an email or Google profile field.
  const checkpoint = await prepareSigninConversion(returnTo, convertAnonymous, handoffToken);
  savePendingWhosGoingFromReturnTo(returnTo);
  const callback = new URL(authCallbackRoute(returnTo, handoffToken ?? checkpoint?.token), origin);
  callback.searchParams.set("method", "google"); // Presentation hint, not authorisation.
  const { error } = await client.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: callback.href },
  });
  if (error) throw error;
}
