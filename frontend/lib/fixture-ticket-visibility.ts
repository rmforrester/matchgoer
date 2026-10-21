/** Compare venue calendar days, never elapsed kickoff hours or viewer dates. */
export function ticketVisibleOnMatchday(fixtureDate?: string | null, venueTimezone?: string | null, now = new Date()): boolean {
  if (!fixtureDate || !venueTimezone || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(fixtureDate) || venueTimezone.startsWith("Etc/")) return false;
  const kickoff = new Date(fixtureDate);
  if (!Number.isFinite(kickoff.getTime()) || !Number.isFinite(now.getTime())) return false;
  try {
    const formatter = new Intl.DateTimeFormat("en-CA", { timeZone: venueTimezone, year: "numeric", month: "2-digit", day: "2-digit" });
    const day = (value: Date) => {
      const parts = formatter.formatToParts(value);
      return ["year", "month", "day"].map(type => parts.find(part => part.type === type)!.value).join("-");
    };
    return day(now) <= day(kickoff);
  } catch { return false; }
}
