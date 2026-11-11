"use client";

import { useEffect, useId, useRef } from "react";
import HistoryActionIcon from "./HistoryActionIcon";

export default function HistoryConfirmation({ open, title, description, label, busy, error, onCancel, onConfirm }: {
  open: boolean; title: string; description: string; label: string; busy: boolean; error: string;
  onCancel: () => void; onConfirm: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open || !dialog.current) return;
    const element = dialog.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow;
    element.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      element.close();
      document.body.style.overflow = overflow;
      if (opener?.isConnected) opener.focus({ preventScroll: true });
      else {
        const heading = document.querySelector<HTMLElement>("main h1");
        heading?.setAttribute("tabindex", "-1");
        heading?.focus({ preventScroll: true });
      }
    };
  }, [open]);
  if (!open) return null;
  return <dialog ref={dialog} aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`}
    onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}
    className="tt-panel tt-history-confirmation fixed max-h-[85dvh] max-w-md overflow-y-auto p-5 text-[var(--tt-ink)] backdrop:bg-black/60">
    <div aria-hidden="true" className="mx-auto mb-4 h-1 w-10 rounded-full bg-[var(--tt-muted)]/50 sm:hidden"/>
    {label === "Remove Ground" && <div className="mb-3 flex justify-center text-[var(--brand-interactive)]"><HistoryActionIcon action="ground"/></div>}
    <h2 id={`${id}-title`} className="tt-display text-center text-3xl">{title}</h2>
    <p id={`${id}-description`} className="mt-3 text-center text-sm leading-relaxed">{description}</p>
    {error && <p role="alert" className="mt-3 text-sm font-bold text-red-800">{error}</p>}
    <div className="mt-5 grid grid-cols-2 gap-2">
      <button autoFocus type="button" disabled={busy} onClick={onCancel} className="tt-action tt-action-secondary min-h-11 px-3">Cancel</button>
      <button type="button" disabled={busy} aria-busy={busy} onClick={onConfirm} className="tt-action tt-action-danger inline-flex min-h-11 items-center justify-center gap-2 px-3"><HistoryActionIcon action={label === "Remove Ground" ? "ground" : "matchday"}/>{busy ? "Removing..." : label}</button>
    </div>
  </dialog>;
}
