export type FixtureStatusGroup = "upcoming" | "live" | "finished" | "postponed" | "cancelled";

const finished = new Set(["FT", "AET", "PEN"]);
const live = new Set(["1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"]);
const postponed = new Set(["PST"]);
const cancelled = new Set(["CANC", "ABD", "AWD", "WO"]);

export function fixtureStatusGroup(status: string | null | undefined): FixtureStatusGroup {
  const value = (status ?? "NS").toUpperCase();
  if (finished.has(value)) return "finished";
  if (live.has(value)) return "live";
  if (postponed.has(value)) return "postponed";
  if (cancelled.has(value)) return "cancelled";
  return "upcoming";
}

export function fixtureStatusLabel(status: string | null | undefined): string {
  const value = (status ?? "NS").toUpperCase();
  if (value === "FT") return "Full time";
  if (value === "AET") return "After extra time";
  if (value === "PEN") return "After penalties";
  if (postponed.has(value)) return "Postponed";
  if (cancelled.has(value)) return value === "ABD" ? "Abandoned" : "Cancelled";
  if (live.has(value)) return value === "HT" ? "Half time" : "Live";
  return "Scheduled";
}
