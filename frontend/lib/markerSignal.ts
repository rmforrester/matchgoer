import { safeFixtureType } from "./fixtureType.ts";

export type MarkerSignal = "international" | "cup" | "rivalry" | "scenic" | "classic" | "standard";

export function markerSignalForFixture(fixture: {
  fixture_type?: string | null;
  decision_attribute_keys?: string[] | null;
}): MarkerSignal {
  const fixtureType = safeFixtureType(fixture.fixture_type);
  if (fixtureType === "international") return "international";
  if (fixtureType === "cup") return "cup";

  const attributes = new Set(fixture.decision_attribute_keys ?? []);
  if (attributes.has("SIGNIFICANT_RIVALRY")) return "rivalry";
  if (attributes.has("FOOTBALL_LANDMARK") || attributes.has("UNIQUE_SETTING")) return "scenic";
  if (attributes.has("CLASSIC_GROUND")) return "classic";
  return "standard";
}
