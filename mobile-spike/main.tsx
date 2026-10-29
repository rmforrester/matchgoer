import {Suspense,use,useMemo,useEffect,useState,type ReactNode} from "react";import {createRoot} from "react-dom/client";
import {NativeAuth,routeNativeReturn} from "./native-auth-return";
import {useLocation} from "./compat/navigation";
import AuthProvider from "../frontend/app/components/AuthProvider";
import Navigation from "./NativeNavigation";
import Discover from "../frontend/app/page";
import Fixture from "../frontend/app/fixture/[fixtureId]/page";
import Venue from "../frontend/app/venue/[venueId]/page";
import MyFootball from "../frontend/app/my-football/page";
import Terraces from "../frontend/app/from-the-terraces/page";
import AccountReady from "../frontend/app/account/ready/page";
import AccountConflict from "../frontend/app/account/conflict/page";
import Account from "../frontend/app/account/page";
import Signin from "../frontend/app/signin/SigninForm";
import Signup from "../frontend/app/signup/SignupForm";
import Callback from "../frontend/app/auth/callback/AuthCallback";
import AuthEmailForm from "../frontend/app/components/AuthEmailForm";
import Recovery from "../frontend/app/auth/recovery/Recovery";
import Privacy from "../frontend/app/privacy/page";
// These existing shared pages only await query parameters and compose AccountShell.
// Resolve their element in the router, rather than rendering an async client component.
function ResolvedAccountResult({content}:{content:Promise<ReactNode>}){return use(content)}
function App(){const [returnError,setReturnError]=useState(false);useEffect(()=>{let listener:{remove:()=>Promise<void>}|undefined;let stopped=false;const receive=({url}:{url?:string})=>{if(url)try{routeNativeReturn(url);}catch{setReturnError(true);}};void NativeAuth.addListener("authReturn",receive).then(value=>{if(stopped)void value.remove();else listener=value;}).catch(()=>{});void NativeAuth.getPendingReturn().then(receive).catch(()=>{});return ()=>{stopped=true;void listener?.remove();};},[]);const url=useLocation();const [path,query]=url.split("?");const search=useMemo(()=>Promise.resolve(Object.fromEntries(new URLSearchParams(query))),[query]);const id=useMemo(()=>path.match(/^\/(fixture|venue)\/(\d+)$/),[path]);const params=useMemo(()=>Promise.resolve(id?{fixtureId:id[2],venueId:id[2]}:{}),[id]);const q=new URLSearchParams(query);const accountResult=useMemo(()=>path==="/account/ready"?AccountReady({searchParams:search}):path==="/account/conflict"?AccountConflict({searchParams:search}):null,[path,search]);let screen;
if(id?.[1]==="fixture")screen=<Fixture params={params as Promise<{fixtureId:string}>} searchParams={search}/>;
else if(id?.[1]==="venue")screen=<Venue params={params as Promise<{venueId:string}>}/>;
else if(path==="/my-football"||path==="/my-stadiums"||path==="/interested")screen=<MyFootball/>;
else if(path==="/from-the-terraces")screen=<Terraces/>;
else if(accountResult)screen=<ResolvedAccountResult content={accountResult}/>;
else if(path==="/account")screen=<Account/>;
else if(path==="/signin")screen=<Signin returnTo={q.get("returnTo")??undefined} handoffToken={q.get("handoff")??undefined} convertAnonymous={q.get("convert")==="1"}/>;
else if(path==="/signup")screen=<Signup returnTo={q.get("returnTo")??undefined}/>;
else if(path==="/auth/forgot-password")screen=<AuthEmailForm kind="recovery" returnTo={q.get("returnTo")??undefined}/>;
else if(path==="/auth/confirm")screen=<AuthEmailForm kind="signup" returnTo={q.get("returnTo")??undefined}/>;
else if(path==="/auth/recovery")screen=<Recovery returnTo={q.get("returnTo")??undefined} providerError={Boolean(q.get("error"))}/>;
else if(path==="/auth/callback")screen=<Callback code={q.get("code")??undefined} returnTo={q.get("returnTo")??undefined} handoffToken={q.get("handoff")??undefined} providerError={q.get("error")??undefined} google={q.get("method")==="google"}/>;
else if(path==="/privacy")screen=<Privacy/>;
else if(path==="/")screen=<Discover/>;
else screen=<main><h1>Route not yet included in this feasibility spike</h1></main>;
return <AuthProvider><Suspense fallback={<p>Loading Matchgoer?</p>}><Navigation/>{returnError&&<p role="alert" className="mx-4 my-3 text-sm text-red-800">We couldn&apos;t validate that sign-in link. Request a new link or sign in again. Your saved history remains unchanged.</p>}{screen}</Suspense></AuthProvider>}
createRoot(document.getElementById("root")!).render(<App/>);
