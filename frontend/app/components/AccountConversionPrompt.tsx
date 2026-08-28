"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { accountRoute, signinRoute } from "@/lib/auth-flow";

type Props = { open: boolean; kind: "interested" | "mate" | "board"; onDismiss: () => void; returnTo?: string };

export default function AccountConversionPrompt({ open, kind, onDismiss, returnTo }: Props) {
  const pathname = usePathname();
  if (!open) return null;
  const mate = kind === "mate";
  const board = kind === "board";
  return (
    <aside role="dialog" aria-modal="false" aria-labelledby="account-prompt-title" className="tt-panel fixed inset-x-3 bottom-3 z-50 mx-auto max-w-lg border-l-[8px] border-l-[var(--tt-blue)] p-5 text-[var(--tt-ink)] sm:bottom-6">
      <h2 id="account-prompt-title" className="tt-display text-2xl">{mate ? "Who's Going?" : board ? "Join the Match Board" : "Going to this one?"}</h2>
      <p className="mt-2 text-[var(--tt-muted)]">{mate ? "Create a Matchgoer account to connect with other supporters going to this match. Account setup takes about a minute." : board ? "Create a Matchgoer account to join the conversation for this match. Account setup takes about a minute." : "Create an account to join the match conversation, save your football across devices and connect with other supporters going. Account setup takes about a minute."}</p>
      <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button type="button" onClick={onDismiss} className="tt-action tt-action-secondary px-4">Maybe later</button>
        <Link href={signinRoute(returnTo ?? pathname, null, true)} className="tt-action tt-action-secondary inline-flex items-center justify-center px-4">Sign in</Link>
        <Link href={accountRoute("/signup", returnTo ?? pathname)} className="tt-action inline-flex items-center justify-center px-4">Create account</Link>
      </div>
    </aside>
  );
}
