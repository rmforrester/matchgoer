import type { MyGround } from "../app/types/grounds.ts";

export type TerracePhoto = {
  photo_id: number; venue_id: number; fixture_id: number | null;
  caption: string | null; display_name: string; match_date: string | null;
  home_team: string | null; away_team: string | null;
  status?: "PENDING" | "APPROVED" | "REJECTED" | "REMOVED";
  upload_state?: "ready" | "incomplete"; held?: boolean;
  image_url?: string; thumbnail_url?: string;
  submitted_at?: string; published_at: string | null;
};
export type PhotoReport = { report_id: number; photo_id: number | null; reason: string; created_at: string };
export type PhotoAttendance = { visit_id: number; venue_id: number; venue_name: string; fixture_id: number | null; match_date: string | null; home_team: string | null; away_team: string | null };

export function recordedPhotoAttendance(grounds: MyGround[]): PhotoAttendance[] {
  // Each owned recorded visit is authoritative; do not infer attendance from plans.
  return grounds.flatMap(ground => ground.visits.map(visit => {
    const fixture = ground.attended_fixtures.find(item => item.fixture_id === visit.fixture_id);
    return { visit_id: visit.visit_id, venue_id: ground.venue_id, venue_name: ground.venue_name, fixture_id: visit.fixture_id,
      match_date: visit.visit_date, home_team: fixture?.home_team ?? null, away_team: fixture?.away_team ?? null };
  }));
}
export function validatePhotoSelection(files: { size: number; type: string; name: string }[], occupied: number): string | null {
  if (!files.length) return "Choose a photograph.";
  if (files.length + occupied > 3) return "You can have up to three pending or approved photos per matchday.";
  for (const file of files) {
    if (!file.size || file.size > 10_000_000) return "Each photograph must be no larger than 10 MB.";
    if (!["image/jpeg", "image/png", "image/heic", "image/heif"].includes(file.type.toLowerCase()) &&
      !(file.type === "" && /\.(jpe?g|png|heic|heif)$/i.test(file.name))) return "Choose JPEG, PNG, HEIC or HEIF photographs.";
  }
  return null; // The backend independently checks actual bytes and all limits.
}
export function occupiedPhotoSlots(photos: TerracePhoto[]): number {
  return photos.filter(photo => photo.status === "PENDING" || photo.status === "APPROVED").length;
}
export function photoMetadata(caption: string, consent: boolean): string {
  if (caption.length > 200 || !consent) throw new Error("Caption or sharing confirmation missing");
  const bytes = new TextEncoder().encode(JSON.stringify({ caption: caption.trim() || null, public_consent: true, rights_acknowledged: true, consent_version: "terraces-public-v1" }));
  return btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join("")).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
export function terracesError(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 404) return "Photo sharing isn't available here yet, or this matchday is no longer available.";
  if (status === 401) return "Sign in with your verified account to continue.";
  if (status === 403) return "Photo sharing isn't available for this account yet. Use your verified account and your own matchdays.";
  if (status === 409) return "This photo or matchday has changed. Refresh its photos before trying again.";
  if (status === 413) return "Each photograph must be no larger than 10 MB.";
  if (status === 422) return "The photo or details could not be accepted. Check the file and sharing confirmation.";
  if (status === 429) return "We're busy right now. Give it another go in a moment.";
  if (!status || status >= 500) return "Can't connect right now. Try again in a moment.";
  return "That didn't work. Give it another go.";
}
