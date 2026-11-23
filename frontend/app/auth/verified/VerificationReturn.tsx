"use client";

import { useEffect, useRef, useState } from "react";
import AccountShell from "@/app/components/AccountShell";
import { MATCHGOER_DOWNLOAD, verificationAppLink, verificationLanding, type VerificationLanding } from "@/lib/email-verification";

export default function VerificationReturn() {
  const [state, setState] = useState<VerificationLanding | null>(null);
  const captured = useRef<VerificationLanding | null>(null);
  useEffect(() => {
    const result = captured.current ?? verificationLanding(window.location.search, window.location.hash);
    captured.current = result;
    // Do not leave an authentication code/error fragment in browser history or referrers.
    window.history.replaceState(null, "", window.location.pathname);
    const timer = window.setTimeout(() => setState(result), 0);
    return () => window.clearTimeout(timer);
  }, []);
  const title = !state ? "Checking your link" : state.kind === "continue" ? "FINISH VERIFYING YOUR EMAIL"
    : state.kind === "expired" ? "This link has expired" : state.kind === "invalid" ? "This link is unavailable" : "Confirm your email";
  const intro = state?.kind === "continue"
    ? "Open Matchgoer to securely finish setting up your account."
    : "If you already verified your email, sign in. Otherwise, open Matchgoer to request a fresh link.";
  return <AccountShell kicker="Account setup" title={title} intro={intro}>
    {state ? <div className="mt-6 grid gap-3">
      <a className="tt-action inline-flex items-center justify-center px-4" href={verificationAppLink(state, state.kind === "continue" ? undefined : "confirm")}>Open Matchgoer</a>
      {state.kind !== "continue" && <>
      <a className="tt-action tt-action-secondary inline-flex items-center justify-center px-4" href={verificationAppLink(state, "signin")}>Sign in to Matchgoer</a>
      <p className="text-sm">Don&apos;t have the app? <a className="font-bold underline" href={MATCHGOER_DOWNLOAD} rel="noreferrer">Download Matchgoer</a></p>
      </>}
      <p className="text-sm text-[var(--tt-muted)]">{state.kind === "continue" ? "If Matchgoer doesn't open, return to the app and sign in." : "If the app doesn't open, open it from your Home Screen and sign in with your email and password. Use the device where you started signup to keep your saved matchdays."}</p>
    </div> : <p role="status" className="mt-6">Checking your confirmation link…</p>}
  </AccountShell>;
}
