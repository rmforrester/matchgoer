import type { SupabaseClient } from "@supabase/supabase-js";

export function appleSigninEnabled() { return false; }
export async function beginAppleSignin(_client: SupabaseClient, _returnTo: string, _handoffToken?: string, _convertAnonymous?: boolean): Promise<void> {
  void [_client, _returnTo, _handoffToken, _convertAnonymous];
  throw new Error("Apple sign-in is available in the iPhone application only");
}

export async function appleDeletionCode(): Promise<string> { throw new Error("Complete Apple authorization in the iPhone app"); }
