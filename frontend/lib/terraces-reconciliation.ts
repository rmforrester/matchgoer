import type { TerracePhoto } from "./terraces.ts";

export type PhotoDraft = { file: File; caption: string; key: string; attempted: boolean; outcome?: "failed" | "uncertain"; error?: string };
export function reconcilePhotoDrafts(drafts: PhotoDraft[], photos: TerracePhoto[]): PhotoDraft[] {
  return drafts.flatMap(draft => {
    if (!draft.attempted) return [draft];
    const saved = photos.find(photo => photo.submission_key === draft.key);
    if (saved && saved.upload_state === "ready") return [];
    if (saved && (saved.status === "REMOVED" || saved.status === "REJECTED")) return [];
    // A successful authoritative owner read establishes whether the prior
    // request completed. Incomplete reservations resume with the SAME UUID.
    return [{ ...draft, outcome: "failed" as const, error: draft.outcome === "failed" && draft.error ? draft.error : "That photo didn't go through. Give it another go." }];
  });
}
export function photoStatus(photo: TerracePhoto): string {
  if (photo.upload_state === "incomplete") return "Not sent";
  return photo.status === "APPROVED" ? photo.published_at ? "Live" : "Approved" : photo.status === "REJECTED" ? "Rejected" : "Pending";
}
