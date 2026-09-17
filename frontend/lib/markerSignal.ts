import { safeFixtureType } from "./fixtureType.ts";

export type MarkerSignal = "international" | "cup" | "rivalry" | "scenic" | "classic" | "standard";

type MarkerDecisionReason = {
  key: string;
  label: string;
  explanation?: string;
};

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

export function editorialReasonForMarkerSignal(fixture: {
  fixture_type?: string | null;
  decision_attribute_keys?: string[] | null;
  decision_reasons?: MarkerDecisionReason[] | null;
  lead_decision_reason?: MarkerDecisionReason | null;
}): MarkerDecisionReason | null {
  const signal = markerSignalForFixture(fixture);
  const acceptedKeys = signal === "rivalry"
    ? new Set(["SIGNIFICANT_RIVALRY"])
    : signal === "scenic"
      ? new Set(["FOOTBALL_LANDMARK", "UNIQUE_SETTING"])
      : signal === "classic"
        ? new Set(["CLASSIC_GROUND"])
        : null;
  if (!acceptedKeys) return null;

  const matchingReason = (fixture.decision_reasons ?? []).find((reason) => acceptedKeys.has(reason.key));
  if (matchingReason) return matchingReason;
  return fixture.lead_decision_reason && acceptedKeys.has(fixture.lead_decision_reason.key)
    ? fixture.lead_decision_reason
    : null;
}
