/** Display-only: omitted timeZone preserves the browser timezone and DST. */
export function formatKickoffTime(value: string | Date, options: Pick<Intl.DateTimeFormatOptions, "timeZone" | "timeZoneName"> = {}) {
  return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", hour12: true, ...options }).format(new Date(value));
}

export function formatFixtureDistance(miles: number, location?: string) {
  const label = location?.trim();
  const origin = label?.toLowerCase() === "current location" ? "your current location" : label || "the search location";
  return `${miles.toFixed(1)} miles from ${origin}`;
}
