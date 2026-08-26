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

const hiddenGuideTopics = new Set(["safety instructions"]);
const secondaryAtGroundTopics = new Set(["food and drink", "deposit"]);

const publishableFacts = (section: VenueGuideSection) => section.facts.filter((fact) =>
  fact.freshness !== "expired" && !hiddenGuideTopics.has(fact.topic.trim().toLocaleLowerCase())
);

export function googleMapsDirectionsUrl(latitude: number, longitude: number) {
  const destination = encodeURIComponent(`${latitude},${longitude}`);
  return `https://www.google.com/maps/dir/?api=1&destination=${destination}`;
}

export function primaryGuideSections(guide: VenueGuide) {
  return guide.sections
    .filter((section) => ["tickets_entry", "before_match", "at_ground"].includes(section.key))
    .map((section) => ({
      ...section,
      facts: publishableFacts(section).filter((fact) =>
        section.key !== "at_ground" || !secondaryAtGroundTopics.has(fact.topic.trim().toLocaleLowerCase())
      ),
    }))
    .filter((section) => section.facts.length > 0);
}

export function secondaryGuideSections(guide: VenueGuide) {
  return guide.sections
    .filter((section) => ["getting_there", "at_ground", "getting_back"].includes(section.key))
    .map((section) => ({
      ...section,
      facts: publishableFacts(section).filter((fact) =>
        section.key !== "at_ground" || secondaryAtGroundTopics.has(fact.topic.trim().toLocaleLowerCase())
      ),
    }))
    .filter((section) => section.facts.length > 0);
}

export function supporterFacingFactContent(fact: VenueGuideFact) {
  if (fact.topic.trim().toLocaleLowerCase() === "matchday ticket offices") {
    return "Tickets are normally available at the stadium ticket offices from one hour before kick-off. Check the fixture announcement for exceptions.";
  }
  return fact.content;
}

export function officialTicketUrl(guide: VenueGuide | null) {
  const ticketSection = guide?.sections.find((section) => section.key === "tickets_entry");
  const onlineTicket = ticketSection?.facts.find((fact) =>
    fact.freshness === "current"
    && fact.topic.trim().toLocaleLowerCase() === "buy online"
    && fact.provenance.label === "Official"
    && fact.provenance.source_url
  );
  return onlineTicket?.provenance.source_url ?? null;
}

export function ticketPresentation(guide: VenueGuide) {
  const facts = primaryGuideSections(guide)
    .find((section) => section.key === "tickets_entry")?.facts ?? [];
  return {
    facts,
    url: officialTicketUrl(guide),
    unknownMessage: facts.length === 0 ? "Ticket information not yet confirmed." : null,
  };
}

export function fixtureGuideActions(guide: VenueGuide, venueId: number) {
  const ticketUrl = officialTicketUrl(guide);
  return [
    { label: "Directions", href: `/venue/${venueId}#directions`, external: false },
    ...(ticketUrl ? [{ label: "Tickets", href: ticketUrl, external: true }] : []),
    { label: "Ground guide", href: `/venue/${venueId}#venue-guide-heading`, external: false },
  ];
}

export function guideSummary(guide: VenueGuide | null) {
  if (!guide?.has_current_information) return null;
  const currentSections = guide.sections.filter((section) =>
    section.facts.some((fact) => fact.freshness === "current")
  );
  if (currentSections.length === 0) return null;
  return {
    sectionCount: currentSections.length,
    labels: currentSections.map((section) => section.label),
    ticketUrl: officialTicketUrl(guide),
  };
}
