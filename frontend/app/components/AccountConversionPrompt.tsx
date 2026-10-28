"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { accountRoute, signinRoute } from "@/lib/auth-flow";

type Props = { open: boolean; kind: "interested" | "mate" | "board"; onDismiss: () => void; returnTo?: string };

export default function AccountConversionPrompt({ open, kind, onDismiss, returnTo }: Props) {
  const pathname = usePathname();
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!open || !dialog.current) return;
    const element = dialog.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    element.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      element.close();
      document.body.style.overflow = previousOverflow;
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, [open]);
  if (!open) return null;
  const mate = kind === "mate";
  const board = kind === "board";
  return (
    <dialog ref={dialog} aria-labelledby="account-prompt-title" onCancel={event => { event.preventDefault(); onDismiss(); }} onClose={() => { if (!dialog.current?.open) onDismiss(); }}
      className="tt-panel fixed m-auto w-[calc(100%-2rem)] overflow-y-auto border-l-[8px] border-l-[var(--brand-interactive)] p-5 text-[var(--tt-ink)] backdrop:bg-black/60"
      style={{ inset: "env(safe-area-inset-top, 0px) env(safe-area-inset-right, 0px) env(safe-area-inset-bottom, 0px) env(safe-area-inset-left, 0px)", maxHeight: "calc(100dvh - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px) - 2rem)", maxWidth: "min(32rem, calc(100vw - env(safe-area-inset-left, 0px) - env(safe-area-inset-right, 0px) - 2rem))" }}>
      <h2 id="account-prompt-title" className="tt-display text-2xl">{mate ? "Who's Going?" : board ? "Join the Match Board" : "Added to My Matchdays"}</h2>
      <p className="mt-2 text-[var(--tt-muted)]">{mate ? "Create a Matchgoer account to connect with other supporters going to this match. Account setup takes about a minute." : board ? "Create a Matchgoer account to join the conversation for this match. Account setup takes about a minute." : "Find it in Interested in My Matchdays. Your guest history is linked to this browser until you transfer it to your account. Clearing browser data or closing a private session can lose access."}</p>
      <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button type="button" onClick={onDismiss} className="tt-action tt-action-secondary px-4">Maybe later</button>
        <Link href={signinRoute(returnTo ?? pathname, null, true)} className="tt-action tt-action-secondary inline-flex items-center justify-center px-4">Sign in</Link>
        <Link href={accountRoute("/signup", returnTo ?? pathname)} className="tt-action inline-flex items-center justify-center px-4">Create account</Link>
      </div>
    </dialog>
  );
}
