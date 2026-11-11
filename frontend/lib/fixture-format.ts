import { localCalendarDateValue } from "./fixtureDiscovery.ts";

/** Display-only: compare calendar dates, never elapsed 24-hour periods. */
export function formatFixtureDate(value: string | Date, now = new Date(), options: Intl.DateTimeFormatOptions = {}, locale?: string) {
  const instant = new Date(value);
  if (!Number.isFinite(instant.getTime())) return "Date to be confirmed";
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: options.timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(instant);
  const part = (type: string) => parts.find(item => item.type === type)!.value;
  const day = `${part("year")}-${part("month")}-${part("day")}`;
  if (day === localCalendarDateValue(now)) return "TODAY";
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  if (day === localCalendarDateValue(tomorrow)) return "TOMORROW";
  return new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "short", ...options }).format(instant);
}

/** Display-only: omitted timeZone preserves the browser timezone and DST. */
export function formatKickoffTime(value: string | Date, options: Pick<Intl.DateTimeFormatOptions, "timeZone" | "timeZoneName"> = {}) {
  return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", hour12: true, ...options }).format(new Date(value));
}

export function formatFixtureDistance(miles: number, location?: string) {
  const label = location?.trim();
  const origin = label?.toLowerCase() === "current location" ? "your current location" : label || "the search location";
  return `${miles.toFixed(1)} miles from ${origin}`;
}
