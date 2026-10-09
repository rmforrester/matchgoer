export const EUROPE_LOCATION_BIAS = "countrycode:al,ad,at,by,be,ba,bg,hr,cy,cz,dk,ee,fi,fr,de,gr,hu,is,ie,it,lv,li,lt,lu,mt,md,mc,me,nl,mk,no,pl,pt,ro,ru,sm,rs,sk,si,es,se,ch,ua,gb,va,tr";
export const AUTOCOMPLETE_DELAY = 275;

export type LocationSuggestion = {
  id: string;
  name: string;
  detail: string;
  label: string;
  latitude: number;
  longitude: number;
};

export function autocompleteParameters(query: string): URLSearchParams | null {
  const text = query.trim();
  if (text.length < 2) return null;
  return new URLSearchParams({ text, format: "json", lang: "en", type: "city", limit: "6", bias: EUROPE_LOCATION_BIAS });
}

// Only exact identifiers / same named coordinate are deduplicated. Different
// administrative subjects remain when the provider does not establish equivalence.
export function locationSuggestions(payload: unknown): LocationSuggestion[] {
  if (!payload || typeof payload !== "object" || !("results" in payload) || !Array.isArray(payload.results)) return [];
  const ids = new Set<string>();
  const coordinates = new Set<string>();
  const suggestions: LocationSuggestion[] = [];
  for (const raw of payload.results) {
    if (!raw || typeof raw !== "object") continue;
    const r = raw as Record<string, unknown>;
    const field = (key: string) => typeof r[key] === "string" ? (r[key] as string).trim() : "";
    const name = field("city") || field("town") || field("name");
    const country = field("country");
    const latitude = r.lat;
    const longitude = r.lon;
    if (!name || !country || typeof latitude !== "number" || typeof longitude !== "number" || !Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) continue;
    const coordinateKey = JSON.stringify([name, country, latitude, longitude]);
    const id = field("place_id") || coordinateKey;
    if (ids.has(id) || coordinates.has(coordinateKey)) continue;
    ids.add(id);
    coordinates.add(coordinateKey);
    const region = field("state") || field("county");
    const detail = [...new Set([region, country].filter(part => part && part !== name))].join(", ");
    suggestions.push({ id, name, detail, label: `${name}, ${detail}`, latitude, longitude });
    if (suggestions.length === 6) break;
  }
  return suggestions;
}
