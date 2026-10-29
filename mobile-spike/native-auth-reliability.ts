import type {SupabaseClient} from "@supabase/supabase-js";
import {safeReturnTo} from "../frontend/lib/auth-flow";
import {NATIVE_CALLBACK,rememberNativeAuth} from "./native-auth-return";
export * from "../frontend/lib/auth-reliability";
export async function requestPasswordRecovery(client:SupabaseClient,email:string,_origin:string,returnTo?:string|null){
 rememberNativeAuth("recovery",safeReturnTo(returnTo,"/account"));
 const {error}=await client.auth.resetPasswordForEmail(email.trim(),{redirectTo:NATIVE_CALLBACK});if(error)throw error;
}
