export type VenueGuideFact = {
  topic: string;
  content: string;
  freshness: "current" | "needs_review" | "expired";
  provenance: { label: string; source_url: string | null; last_checked: string | null };
};

export type VenueGuideSection = {
  key: string;
  label: string;
  facts: VenueGuideFact[];
};

export type VenueGuide = {
  venue_id: number;
  has_current_information: boolean;
  sections: VenueGuideSection[];
};

export function guideSummary(guide: VenueGuide | null) {
  if (!guide?.has_current_information) return null;
  const currentSections = guide.sections.filter((section) =>
    section.facts.some((fact) => fact.freshness === "current")
  );
  if (currentSections.length === 0) return null;
  return {
    sectionCount: currentSections.length,
    labels: currentSections.map((section) => section.label),
  };
}
