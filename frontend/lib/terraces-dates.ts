const dateOptions: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" };

// A recorded match day is a calendar date, not midnight in the viewer's zone.
// Keep the calendar portion of known fixture timestamps too.
export function formatMatchDate(value: string | null | undefined, locale?: string): string | null {
  const match = value?.match(/^(\d{4}-\d{2}-\d{2})(?:$|T)/);
  if (!match) return null;
  const date = new Date(`${match[1]}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== match[1]) return null;
  return date.toLocaleDateString(locale, { ...dateOptions, timeZone: "UTC" });
}

export function formatPublicationDate(value: string | null | undefined, locale?: string): string | null {
  if (!value || !/T.*(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date.toLocaleDateString(locale, dateOptions) : null;
}
