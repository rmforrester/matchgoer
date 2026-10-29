import type {SupabaseClient} from "@supabase/supabase-js";
import {safeReturnTo} from "../frontend/lib/auth-flow";
import {prepareSigninConversion,savePendingWhosGoingFromReturnTo} from "../frontend/lib/account-conversion-checkpoint";
import {NativeAuth,NATIVE_CALLBACK,rememberNativeAuth,routeNativeReturn} from "./native-auth-return";
export {googleCallbackError} from "../frontend/lib/google-signin";
export function googleSigninEnabled(){return process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED==="true";}
export async function beginGoogleSignin(client:SupabaseClient,_origin:string,requestedReturnTo?:string,handoffToken?:string,convertAnonymous=false){
 if(!googleSigninEnabled())throw new Error("Google sign-in unavailable");
 const returnTo=safeReturnTo(requestedReturnTo);await prepareSigninConversion(returnTo,convertAnonymous,handoffToken);savePendingWhosGoingFromReturnTo(returnTo);
 rememberNativeAuth("google",returnTo);
 const {data,error}=await client.auth.signInWithOAuth({provider:"google",options:{redirectTo:NATIVE_CALLBACK,skipBrowserRedirect:true,queryParams:{prompt:"select_account"}}});if(error)throw error;
 const u=new URL(data.url);if(u.origin!==process.env.NEXT_PUBLIC_SUPABASE_URL||u.pathname!=="/auth/v1/authorize"||u.protocol!=="https:"||u.username||u.password||u.searchParams.get("provider")!=="google"||u.searchParams.get("redirect_to")!==NATIVE_CALLBACK||u.searchParams.get("code_challenge_method")!=="s256")throw new Error("Invalid native authorisation URL");
 const result=await NativeAuth.authenticate({url:u.href});routeNativeReturn(result.url);
}
