import type { TerracePhoto } from "./terraces.ts";

export function mergePublicPhotos(current: TerracePhoto[], incoming: TerracePhoto[]): TerracePhoto[] {
  return [...new Map([...current, ...incoming].map(photo => [photo.photo_id, photo])).values()]
    .sort((a, b) => Date.parse(b.published_at ?? "") - Date.parse(a.published_at ?? "") || b.photo_id - a.photo_id);
}
export function groupPublicPhotos(photos: TerracePhoto[]): TerracePhoto[][] {
  const groups = new Map<number, TerracePhoto[]>();
  for (const photo of mergePublicPhotos([], photos)) {
    if (!groups.has(photo.venue_id)) groups.set(photo.venue_id, []);
    groups.get(photo.venue_id)!.push(photo);
  }
  return [...groups.values()];
}

// Unlinked visits have no public visit ID. Only relationships returned by the
// existing matchday_of endpoint may join them; ground/date/name never suffice.
export function mergeHistoricalGroups(current: Record<number, number>, members: number[]): Record<number, number> {
  const related = new Set(members.map(id => current[id] ?? id));
  const representative = Math.min(...related);
  return { ...Object.fromEntries(Object.entries(current).map(([id, group]) => [id, related.has(group) ? representative : group])),
    ...Object.fromEntries(members.map(id => [id, representative])) };
}

export function fixtureGalleryKey(photo: TerracePhoto, historical: Record<number, number> = {}) {
  return photo.fixture_id !== null ? `fixture-${photo.fixture_id}` : `historical-${historical[photo.photo_id] ?? photo.photo_id}`;
}

export function groupFixturePhotos(photos: TerracePhoto[], historical: Record<number, number> = {}): TerracePhoto[][] {
  const groups = new Map<string, TerracePhoto[]>();
  for (const photo of mergePublicPhotos([], photos)) {
    const key = fixtureGalleryKey(photo, historical);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(photo);
  }
  return [...groups.values()];
}
