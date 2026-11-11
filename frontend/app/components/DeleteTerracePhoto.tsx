"use client";

import { useRef, useState } from "react";
import api from "../../lib/api";
import { terracesError, type TerracePhoto } from "../../lib/terraces";
import { useAuth } from "./AuthProvider";
import HistoryConfirmation from "./HistoryConfirmation";

export default function DeleteTerracePhoto({ photo, onDeleted, number }: { photo: TerracePhoto; onDeleted: () => void; number?: number }) {
  const { authenticated } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  if (!authenticated || photo.can_delete !== true) return null;
  async function remove() {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try {
      const { data } = await api.delete(`/terraces/photos/${photo.photo_id}`);
      if (data.status !== "REMOVED" || data.public_visibility !== "removed") throw new Error("Photo removal not confirmed");
      setConfirming(false); onDeleted();
    } catch (failure) { setError(terracesError(failure)); }
    finally { pending.current = false; setBusy(false); }
  }
  return <>
    <button type="button" className="min-h-11 px-2 text-xs font-bold text-red-800 underline" onClick={() => { setError(""); setConfirming(true); }}>Delete photo{number != null ? ` ${number}` : ""}</button>
    <HistoryConfirmation open={confirming} title="DELETE PHOTO?" description="Delete this photo? Your matchday attendance will be kept." label="Delete photo" busy={busy} error={error} onCancel={() => { if (!pending.current) setConfirming(false); }} onConfirm={() => void remove()} />
  </>;
}
