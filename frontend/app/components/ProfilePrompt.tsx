"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import api from "../../lib/api";

type ProfilePromptProps = {
  open: boolean;
  purpose: "meeting" | "message";
  onCancel: () => void;
  onCreated: () => Promise<void> | void;
};

export default function ProfilePrompt({ open, purpose, onCancel, onCreated }: ProfilePromptProps) {
  const [displayName, setDisplayName] = useState("");
  const [supportedClub, setSupportedClub] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const nameInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) nameInput.current?.focus();
  }, [open]);

  if (!open) return null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const name = displayName.trim();
    if (name.length < 2 || name.length > 40) {
      setError("Display name must be 2 to 40 characters.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.post("/profile", {
        display_name: name,
        supported_club: supportedClub.trim() || null,
      });
      await onCreated();
      setDisplayName("");
      setSupportedClub("");
    } catch {
      setError("Unable to create your profile. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-3 sm:items-center" role="presentation">
      <section role="dialog" aria-modal="true" aria-labelledby="profile-prompt-title" className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl sm:p-6">
        <h2 id="profile-prompt-title" className="text-xl font-bold">Create your Terrace Talk profile</h2>
        <p className="mt-2 text-gray-700">
          {purpose === "meeting"
            ? "Create a Terrace Talk profile to join Who's Going? and connect with other supporters."
            : "Create a Terrace Talk profile to message other football fans."}
        </p>
        <form onSubmit={submit} className="mt-5 grid gap-4">
          <label className="grid gap-1 font-medium">Display name *
            <input ref={nameInput} value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={40} autoComplete="nickname" className="min-h-11 rounded-lg border px-3 font-normal" />
          </label>
          <label className="grid gap-1 font-medium">Supported club (optional)
            <input value={supportedClub} onChange={(event) => setSupportedClub(event.target.value)} maxLength={80} className="min-h-11 rounded-lg border px-3 font-normal" />
          </label>
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button type="button" disabled={saving} onClick={onCancel} className="min-h-11 rounded-lg border px-4 font-semibold">Cancel</button>
            <button type="submit" disabled={saving} className="min-h-11 rounded-lg border border-blue-700 bg-blue-700 px-4 font-semibold text-white disabled:opacity-60">{saving ? "Creating…" : "Create profile"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}
