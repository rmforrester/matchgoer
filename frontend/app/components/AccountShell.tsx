import Link from "next/link";
import type { ReactNode } from "react";

export default function AccountShell({ kicker, title, intro, children }: { kicker: string; title: string; intro: string; children: ReactNode }) {
  return <main className="mx-auto w-full max-w-xl px-4 py-8 sm:px-6 sm:py-12">
    <Link href="/" className="tt-display text-xl text-[var(--tt-blue)]">Terrace Talk</Link>
    <section className="tt-panel mt-5 overflow-hidden">
      <div className="border-b-2 border-[var(--tt-ink)] bg-[var(--tt-blue)] px-5 py-3 text-[var(--tt-paper)]"><p className="text-xs font-extrabold uppercase tracking-[0.14em]">{kicker}</p></div>
      <div className="p-5 sm:p-7">
        <h1 className="tt-display text-4xl leading-none sm:text-5xl">{title}</h1>
        <p className="mt-3 max-w-md leading-7 text-[var(--tt-muted)]">{intro}</p>
        {children}
      </div>
    </section>
  </main>;
}
