import {useEffect,useState} from "react";
import Link from "./compat/link";
import Image from "next/image";
import {useLocation} from "./compat/navigation";
import {useAuth} from "../frontend/app/components/AuthProvider";
import {signinRoute} from "../frontend/lib/auth-flow";
import "./native-navigation.css";
const tabs=[
 {label:"Discover",href:"/",icon:<><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>},
 {label:"Matchdays",href:"/my-football?tab=interested",icon:<><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6m10-6v6M3 11h18m-13 4h2m4 0h2"/></>},
 {label:"Grounds",href:"/my-stadiums",icon:<><path d="M3 9v11h18V9L12 5 3 9Zm0 4 9 4 9-4M7 11v9m10-9v9M12 2v3M3 3v6m18-6v6"/></>},
 {label:"Account",href:"/account",icon:<><circle cx="12" cy="7" r="4"/><path d="M4 22v-3a8 8 0 0 1 16 0v3"/></>},
];
export default function NativeNavigation(){
 const url=useLocation();const path=url.split("?")[0];const query=new URLSearchParams(url.split("?")[1]);
 const {logoutError,authenticated}=useAuth();const [keyboard,setKeyboard]=useState(false);
 useEffect(()=>{const viewport=window.visualViewport;if(!viewport)return;
  let fullHeight=viewport.height;
  const update=()=>{const editing=document.activeElement?.matches("input,textarea,select")==true;if(!editing)fullHeight=Math.max(fullHeight,viewport.height);setKeyboard(editing&&fullHeight-viewport.height>150);};
  viewport.addEventListener("resize",update);document.addEventListener("focusout",update);
  return ()=>{viewport.removeEventListener("resize",update);document.removeEventListener("focusout",update);};},[]);
 const active=path==="/"?"Discover":path==="/my-stadiums"||(path==="/my-football"&&query.get("tab")!=="interested")?"Grounds":path==="/interested"||path==="/my-football"||path.startsWith("/fixture/")?"Matchdays":"Account";
 return <><header className="native-header"><Link href="/" aria-label="Matchgoer home"><Image src="/brand/matchgoer-wordmark-primary.png" alt="Matchgoer" width="4202" height="714"/></Link></header>
 {logoutError&&path!=="/account"&&<p role="alert">{logoutError}</p>}
 <nav className="native-tabs" aria-label="Primary navigation" hidden={keyboard}>{tabs.map(tab=><Link key={tab.label} href={tab.label === "Account" && !authenticated ? signinRoute() : tab.href} aria-label={tab.label} aria-current={active===tab.label?"page":undefined}><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{tab.icon}</svg><span>{tab.label}</span></Link>)}</nav></>;
}
