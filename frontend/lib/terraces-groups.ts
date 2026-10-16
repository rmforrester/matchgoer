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
