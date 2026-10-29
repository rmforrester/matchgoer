import {registerPlugin} from "@capacitor/core";
import type {PluginListenerHandle} from "@capacitor/core";
import {safeReturnTo} from "../frontend/lib/auth-flow";
import {navigate} from "./compat/navigation";
export const NATIVE_CALLBACK="com.matchgoer.app://auth/callback";
export const NativeAuth=registerPlugin<{authenticate(options:{url:string}):Promise<{url:string}>;getPendingReturn():Promise<{url?:string}>;addListener(name:"authReturn",listener:(data:{url:string})=>void):Promise<PluginListenerHandle>}>("MatchgoerAuth");
const key="matchgoer.native.auth-return.v1";
export function rememberNativeAuth(kind:"google"|"recovery",returnTo:string){localStorage.setItem(key,JSON.stringify({kind,returnTo:safeReturnTo(returnTo),expires:Date.now()+60*60*1000}));}
export function nativeCallbackCode(raw:string){const u=new URL(raw);if(u.protocol!=="com.matchgoer.app:"||u.hostname!=="auth"||u.pathname!=="/callback"||u.port||u.username||u.password||u.hash||u.searchParams.has("access_token")||u.searchParams.has("refresh_token"))throw new Error("Unexpected auth return");
 const code=u.searchParams.get("code");if(u.searchParams.getAll("code").length>1)throw new Error("Ambiguous auth return");if(!code&&!u.searchParams.has("error"))throw new Error("Missing auth code");return {code,error:u.searchParams.has("error")?"access_denied":null};}
let lastReturn="";
export function routeNativeReturn(raw:string){if(lastReturn===raw)return;const result=nativeCallbackCode(raw);let pending;try{pending=JSON.parse(localStorage.getItem(key)??"null");}catch{}
 if(!pending||pending.expires<Date.now()||!["google","recovery"].includes(pending.kind))throw new Error("No pending authentication");
 lastReturn=raw;const q=new URLSearchParams({returnTo:safeReturnTo(pending.returnTo)});if(result.code)q.set("code",result.code);if(result.error)q.set("error",result.error);if(pending.kind==="google")q.set("method","google");
 // Shared AuthCallback exchanges the PKCE code and performs the guarded claim.
 // PASSWORD_RECOVERY events instead route to the shared recovery screen.
 navigate("/auth/callback?"+q,true);
}
