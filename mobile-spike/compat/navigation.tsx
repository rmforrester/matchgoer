import {useSyncExternalStore} from "react";
const subscribe=(fn:()=>void)=>{window.addEventListener("popstate",fn);return ()=>window.removeEventListener("popstate",fn)};
export function useLocation(){return useSyncExternalStore(subscribe,()=>location.pathname+location.search,()=>"/")}
export function navigate(href:string,replace=false){const u=new URL(href,location.href);if(u.origin!==location.origin){window.open(u.href,"_blank","noopener");return}history[replace?"replaceState":"pushState"]({},"",u.pathname+u.search+u.hash);dispatchEvent(new PopStateEvent("popstate"))}
export function usePathname(){return useLocation().split("?")[0]}
export function useSearchParams(){return new URLSearchParams(useLocation().split("?")[1]??"")}
const router={push:(s:string)=>navigate(s),replace:(s:string)=>navigate(s,true),back:()=>history.back(),refresh:()=>dispatchEvent(new PopStateEvent("popstate")),prefetch:()=>Promise.resolve()};
export function useRouter(){return router}
