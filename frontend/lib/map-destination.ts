export type MapPlatform = "apple" | "google";
export function mapPlatform(): MapPlatform {
  return typeof navigator !== "undefined" && (/iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)) ? "apple" : "google";
}
export function coordinatePlaceUrl(latitude: number, longitude: number, name = "", platform: MapPlatform = "google"): string | null {
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180 || (latitude === 0 && longitude === 0)) return null;
  const point = `${latitude},${longitude}`;
  if (platform === "apple") {
    const params = new URLSearchParams({ coordinate: point });
    if (name.trim()) params.set("name", name.trim());
    return `https://maps.apple.com/place?${params}`;
  }
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(point)}`;
}

/** Only a previously verified, supported destination is accepted. Never geocode or guess. */
export function placeUrlFromVerifiedUrl(value: string | null, platform: MapPlatform = "google", destinationName = ""): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.username || url.password) return null;
    if (["www.google.com", "maps.google.com", "google.com"].includes(url.hostname)) {
      if (!/^\/maps\/(search|dir)\/?$/.test(url.pathname)) return null;
      const query = url.searchParams.get("query") || url.searchParams.get("destination");
      if (!query?.trim() || query.length > 1000) return null;
      const coordinate = query.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
      if (coordinate && !coordinatePlaceUrl(Number(coordinate[1]), Number(coordinate[2]))) return null;
      const place = url.searchParams.get("query_place_id") || url.searchParams.get("destination_place_id");
      if (platform === "apple" && !place) {
        const point = query.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
        if (point) return coordinatePlaceUrl(Number(point[1]), Number(point[2]), destinationName, "apple");
        return `https://maps.apple.com/place?${new URLSearchParams({ address: query })}`;
      }
      // A Google Place ID cannot safely be translated into an Apple Place ID.
      const params = new URLSearchParams({ api: "1", query });
      if (place) params.set("query_place_id", place);
      return `https://www.google.com/maps/search/?${params}`;
    }
    if (url.hostname === "maps.apple.com" && url.pathname === "/place") {
      const params = new URLSearchParams();
      for (const key of ["coordinate", "address", "place-id", "name"]) {
        const item = url.searchParams.get(key); if (item) params.set(key, item);
      }
      if (!params.has("coordinate") && !params.has("address") && !params.has("place-id")) return null;
      return `https://maps.apple.com/place?${params}`;
    }
    return null;
  } catch { return null; }
}
