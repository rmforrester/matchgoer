export type FixtureType = "standard" | "cup" | "international";

export function safeFixtureType(value: string | null | undefined): FixtureType {
  return value === "cup" || value === "international" ? value : "standard";
}

export function fixtureTypeLabel(type: FixtureType): string {
  if (type === "cup") return "Cup fixture";
  if (type === "international") return "International fixture";
  return "Standard fixture";
}
