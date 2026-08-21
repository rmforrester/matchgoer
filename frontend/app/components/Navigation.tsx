"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "./AuthProvider";

export default function Navigation() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { authenticated, loading, profile, signOut } = useAuth();
  const linkClass = (active: boolean) =>
    `border-b-2 py-1 transition ${active ? "border-[var(--tt-blue)] text-[var(--tt-blue)]" : "border-transparent hover:border-[var(--tt-blue)] hover:text-[var(--tt-blue)]"}`;
  const myFootballTab = searchParams.get("tab");
  const matchdaysActive = pathname === "/interested"
    || (pathname === "/my-football" && myFootballTab === "interested")
    || pathname.startsWith("/fixture/");
  const groundsActive = pathname === "/my-stadiums"
    || (pathname === "/my-football" && myFootballTab !== "interested");

  return (
    <header className="border-b-2 border-[var(--tt-ink)] bg-[var(--tt-paper)]">
      <div className="mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-x-3 gap-y-2 px-4 py-3 sm:px-6 sm:py-4">

        <Link
          href="/"
          className="tt-display shrink-0 text-2xl leading-none text-[var(--tt-ink)] hover:text-[var(--tt-blue)] sm:text-[2rem]"
        >
          Matchgoer
        </Link>

        <nav aria-label="Primary navigation" className="flex min-w-0 flex-1 justify-end gap-x-3 text-[0.65rem] font-extrabold uppercase tracking-[0.06em] sm:gap-x-5 sm:text-xs sm:tracking-[0.1em]">
          <Link href="/" aria-current={pathname === "/" ? "page" : undefined} className={linkClass(pathname === "/")}>Discover</Link>
          <Link href="/my-football?tab=interested" aria-current={matchdaysActive ? "page" : undefined} className={linkClass(matchdaysActive)}>My Matchdays</Link>
          <Link href="/my-stadiums" aria-current={groundsActive ? "page" : undefined} className={linkClass(groundsActive)}>My Grounds</Link>
        </nav>

        <div className="flex w-full items-center justify-end gap-3 border-t border-[var(--tt-rule)] pt-2 text-[0.65rem] font-extrabold uppercase tracking-[0.08em] sm:w-auto sm:border-l sm:border-t-0 sm:pl-3 sm:pt-0">
          {!loading && authenticated ? <>
            <span className="max-w-32 truncate text-[var(--tt-blue)]">{profile?.username ? `@${profile.username}` : profile?.display_name || "Account"}</span>
            <button type="button" className="min-h-11 underline decoration-2 underline-offset-4" onClick={() => void signOut().then(() => router.push("/"))}>Log out</button>
          </> : !loading ? <>
            <Link href="/signup" className="min-h-11 content-center text-[var(--tt-blue)]">Create account</Link>
            <Link href="/signin" className="min-h-11 content-center underline decoration-2 underline-offset-4">Sign in</Link>
          </> : <span className="min-h-11 content-center text-[var(--tt-muted)]">Account</span>}
        </div>

      </div>
    </header>
  );
}
