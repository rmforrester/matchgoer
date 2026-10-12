"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "./AuthProvider";
import LogoutButton from "./LogoutButton";

const subscribeToHydration = () => () => {};
const clientHydrationSnapshot = () => true;
const serverHydrationSnapshot = () => false;

export default function Navigation() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { authenticated, loading, issue, logoutError, profile, email } = useAuth();
  const [accountOpen, setAccountOpen] = useState(false);
  const accountControl = useRef<HTMLDivElement>(null);
  const accountButton = useRef<HTMLButtonElement>(null);
  const displayName = profile?.display_name || "Account";
  useEffect(() => {
    if (!accountOpen) return;
    function outside(event: PointerEvent) {
      if (!accountControl.current?.contains(event.target as Node)) setAccountOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setAccountOpen(false);
        accountButton.current?.focus();
      }
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [accountOpen]);
  const hydrated = useSyncExternalStore(subscribeToHydration, clientHydrationSnapshot, serverHydrationSnapshot);
  const linkClass = (active: boolean) =>
    `border-b-2 py-1 transition ${active ? "border-[var(--brand-interactive)] text-[var(--brand-interactive)]" : "border-transparent hover:border-[var(--brand-interactive)] hover:text-[var(--brand-interactive)]"}`;
  const myFootballTab = searchParams.get("tab");
  const matchdaysActive = pathname === "/interested"
    || (pathname === "/my-football" && myFootballTab === "interested")
    || pathname.startsWith("/fixture/");
  const groundsActive = pathname === "/my-stadiums"
    || (pathname === "/my-football" && myFootballTab !== "interested");

  return (
    <header className="border-b-2 border-[var(--tt-ink)] bg-[var(--tt-paper)]">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-3 sm:px-6 sm:py-4">

        <Link
          href="/"
          aria-label="Matchgoer home"
          className="shrink-0"
        >
          <Image src="/brand/matchgoer-wordmark-primary.png" alt="Matchgoer" width={4202} height={714} className="h-auto w-[7.75rem] sm:w-[10.5rem]" priority />
        </Link>

        <nav aria-label="Primary navigation" className="order-3 flex w-full min-w-0 justify-between gap-x-3 border-t border-[var(--tt-rule)] pt-2 text-[0.6rem] font-extrabold uppercase tracking-[0.04em] sm:order-none sm:w-auto sm:flex-1 sm:justify-end sm:gap-x-5 sm:border-0 sm:pt-0 sm:text-xs sm:tracking-[0.1em]">
          <Link href="/" aria-current={pathname === "/" ? "page" : undefined} className={linkClass(pathname === "/")}>Discover</Link>
          <Link href="/my-football?tab=interested" aria-current={matchdaysActive ? "page" : undefined} className={linkClass(matchdaysActive)}>My Matchdays</Link>
          <Link href="/my-stadiums" aria-current={groundsActive ? "page" : undefined} className={linkClass(groundsActive)}>My Grounds</Link>
        </nav>

        <div className="flex w-auto items-center justify-end gap-3 text-[0.6rem] font-extrabold uppercase tracking-[0.04em] sm:border-l sm:pl-3 sm:text-[0.65rem] sm:tracking-[0.08em]">
          {hydrated && !loading && authenticated ? <div ref={accountControl} className="relative" onBlur={event => {
            if (!event.currentTarget.contains(event.relatedTarget)) setAccountOpen(false);
          }}>
            <button ref={accountButton} type="button" aria-expanded={accountOpen} aria-controls="navigation-account" aria-label={`Account options for ${displayName}`} onClick={() => setAccountOpen(!accountOpen)} className="flex min-h-11 max-w-[9rem] items-center gap-1 text-[var(--brand-interactive)] focus-visible:outline-2 focus-visible:outline-offset-2 sm:max-w-[12rem]">
              <span className="truncate">{displayName}</span><span aria-hidden="true">▾</span>
            </button>
            {accountOpen && <div id="navigation-account" role="region" aria-label="Account options" className="absolute right-0 top-full z-50 w-[min(18rem,calc(100vw-2rem))] border border-[var(--brand-interactive)] bg-[var(--tt-paper)] p-3 text-sm font-normal normal-case tracking-normal">
              <p className="break-words font-bold">{displayName}</p>
              <p className="break-all pb-3 text-[var(--tt-muted)]">{email}</p>
              <div className="border-t border-[var(--tt-rule)] pt-1">
                <Link href="/account" onClick={() => setAccountOpen(false)} aria-current={pathname === "/account" ? "page" : undefined} className="block min-h-11 content-center font-bold underline underline-offset-4 focus-visible:outline-2">My Account</Link>
                <LogoutButton className="block min-h-11 w-full text-left font-bold underline underline-offset-4 focus-visible:outline-2" onSuccess={() => { setAccountOpen(false); router.push("/"); }} />
              </div>
            </div>}
          </div> : hydrated && !loading && issue === "unavailable" ? <Link href="/account" className="min-h-11 content-center text-[var(--brand-interactive)]">My Account</Link> : hydrated && !loading ? <>
            <Link href="/signup" className="min-h-11 content-center text-[var(--brand-interactive)]">Create account</Link>
            <Link href="/signin" className="min-h-11 content-center underline decoration-2 underline-offset-4">Sign in</Link>
          </> : <span className="min-h-11 content-center text-[var(--tt-muted)]">Account</span>}
        </div>

      </div>
      {logoutError && pathname !== "/account" && <p role="alert" className="mx-auto max-w-6xl px-4 pb-3 text-sm text-red-800 sm:px-6">{logoutError}</p>}
    </header>
  );
}
