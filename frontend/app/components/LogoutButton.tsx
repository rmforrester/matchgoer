"use client";
import { useState } from "react";
import { useAuth } from "./AuthProvider";

export default function LogoutButton({ onSuccess, className = "min-h-11 underline decoration-2 underline-offset-4" }: { onSuccess: () => void; className?: string }) {
  const { signOut } = useAuth();
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true);
    try { await signOut(); onSuccess(); }
    catch { /* AuthProvider retains an honest notice even if the SDK clears local auth. */ }
    finally { setBusy(false); }
  }
  return <button type="button" disabled={busy} className={className} onClick={() => void submit()}>{busy ? "Logging out…" : "Log out"}</button>;
}
