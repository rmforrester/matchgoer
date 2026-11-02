import { registerPlugin } from "@capacitor/core";
import type { SupabaseClient } from "@supabase/supabase-js";
import { safeReturnTo } from "../frontend/lib/auth-flow";
import { prepareSigninConversion, savePendingWhosGoingFromReturnTo } from "../frontend/lib/account-conversion-checkpoint";
import { navigate } from "./compat/navigation";

const Apple = registerPlugin<{ signInWithApple(): Promise<{ identityToken: string; nonce: string; authorizationCode?: string }> }>("MatchgoerAuth");
export async function appleDeletionCode() {
  const credential = await Apple.signInWithApple();
  if (!credential.authorizationCode) throw new Error("Apple authorization is required");
  return credential.authorizationCode;
}
export function appleSigninEnabled() { return true; }
export async function beginAppleSignin(client: SupabaseClient, destination: string, handoffToken?: string, convertAnonymous = false) {
  const returnTo = safeReturnTo(destination);
  await prepareSigninConversion(returnTo, convertAnonymous, handoffToken);
  savePendingWhosGoingFromReturnTo(returnTo);
  const credential = await Apple.signInWithApple();
  if (!credential.identityToken || !credential.nonce) throw new Error("Apple authentication did not return safely");
  const { data, error } = await client.auth.signInWithIdToken({ provider: "apple", token: credential.identityToken, nonce: credential.nonce });
  if (error) throw error;
  if (!data.session) throw new Error("Apple authentication did not create a session");
  // No Apple tokens in URLs or storage. Shared callback performs the existing
  // owner-verified claim using the explicit handoff/checkpoint exactly once.
  const query = new URLSearchParams({ returnTo });
  if (handoffToken) query.set("handoff", handoffToken);
  navigate("/auth/callback?" + query, true);
}
