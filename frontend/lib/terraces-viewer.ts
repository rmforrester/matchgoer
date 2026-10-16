import type { TerracePhoto } from "./terraces.ts";

export function publicMatchdayParams(photo: TerracePhoto, cursor?: string) {
  return { limit: 24, cursor, ...(photo.fixture_id != null
    ? { venue_id: photo.venue_id, fixture_id: photo.fixture_id }
    : { matchday_of: photo.photo_id }) };
}

export function viewerStepIndex(photos: TerracePhoto[], currentId: number, step: -1 | 1): number | null {
  const current = photos.findIndex(photo => photo.photo_id === currentId);
  const next = current + step;
  return next >= 0 && next < photos.length ? next : null;
}
