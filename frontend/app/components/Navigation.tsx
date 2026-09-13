"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "./AuthProvider";

export default function Navigation() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { authenticated, loading, profile, signOut } = useAuth();
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
          className="shrink-0 rounded-sm focus-visible:outline-offset-4"
          aria-label="Matchgoer home"
        >
          <Image
            src="/brand/matchgoer-wordmark-primary.svg"
            alt="Matchgoer"
            width={1800}
            height={306}
            priority
            className="h-auto w-[6.25rem] sm:w-[10.5rem]"
          />
        </Link>

        <nav aria-label="Primary navigation" className="order-3 flex w-full min-w-0 justify-between gap-x-3 border-t border-[var(--tt-rule)] pt-2 text-[0.6rem] font-extrabold uppercase tracking-[0.04em] sm:order-none sm:w-auto sm:flex-1 sm:justify-end sm:gap-x-5 sm:border-0 sm:pt-0 sm:text-xs sm:tracking-[0.1em]">
          <Link href="/" aria-current={pathname === "/" ? "page" : undefined} className={linkClass(pathname === "/")}>Discover</Link>
          <Link href="/my-football?tab=interested" aria-current={matchdaysActive ? "page" : undefined} className={linkClass(matchdaysActive)}>My Matchdays</Link>
          <Link href="/my-stadiums" aria-current={groundsActive ? "page" : undefined} className={linkClass(groundsActive)}>My Grounds</Link>
        </nav>

        <div className="flex w-auto items-center justify-end gap-3 text-[0.6rem] font-extrabold uppercase tracking-[0.04em] sm:border-l sm:pl-3 sm:text-[0.65rem] sm:tracking-[0.08em]">
          {!loading && authenticated ? <>
            <span className="max-w-32 truncate text-[var(--brand-interactive)]">{profile?.username ? `@${profile.username}` : profile?.display_name || "Account"}</span>
            <button type="button" className="min-h-11 underline decoration-2 underline-offset-4" onClick={() => void signOut().then(() => router.push("/"))}>Log out</button>
          </> : !loading ? <>
            <Link href="/signup" className="min-h-11 content-center text-[var(--brand-interactive)]">Create account</Link>
            <Link href="/signin" className="min-h-11 content-center underline decoration-2 underline-offset-4">Sign in</Link>
          </> : <span className="min-h-11 content-center text-[var(--tt-muted)]">Account</span>}
        </div>

      </div>
    </header>
  );
}
