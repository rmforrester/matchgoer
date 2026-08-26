import assert from "node:assert/strict";
import test from "node:test";
import { fixtureGuideActions, googleMapsDirectionsUrl, guideSummary, officialTicketUrl, primaryGuideSections, secondaryGuideSections, supporterFacingFactContent, ticketPresentation, type VenueGuide } from "./venue-guide.ts";

const guide = (freshness: "current" | "needs_review" | "expired"): VenueGuide => ({
  venue_id: 22950,
  has_current_information: freshness === "current",
  sections: [{
    key: "getting_there",
    label: "Getting there",
    facts: [{
      topic: "development transport proof",
      content: "Development-only guidance",
      freshness,
      provenance: { label: "Official", source_url: null, last_checked: "2026-08-21" },
    }],
  }],
});

test("fixture with current guide gets a compact summary", () => {
  assert.deepEqual(guideSummary(guide("current")), {
    sectionCount: 1,
    labels: ["Getting there"],
    ticketUrl: null,
  });
});

test("fixture without guide fails gracefully", () => {
  assert.equal(guideSummary(null), null);
});

test("a guide without ticket evidence gives an honest unknown state", () => {
  assert.equal(ticketPresentation(guide("current")).unknownMessage, "Ticket information not yet confirmed.");
});

test("stale-only guide does not claim current fixture guidance", () => {
  assert.equal(guideSummary(guide("expired")), null);
});

test("directions use canonical coordinates without storing a journey", () => {
  assert.equal(
    googleMapsDirectionsUrl(50.066111, 20.057222),
    "https://www.google.com/maps/dir/?api=1&destination=50.066111%2C20.057222"
  );
});

test("practical guide keeps answers primary and moves supporting facts deeper", () => {
  const hutnikGuide: VenueGuide = {
    venue_id: 22950,
    has_current_information: true,
    sections: [
      { key: "getting_there", label: "Getting there", facts: [
        { topic: "Nearest tram stop", content: "Use Suche Stawy.", freshness: "current", provenance: { label: "Official", source_url: "https://example.com/travel", last_checked: "2026-08-21" } },
        { topic: "Bus alternatives", content: "Other stops.", freshness: "current", provenance: { label: "Official", source_url: null, last_checked: "2026-08-21" } },
        { topic: "From central Kraków", content: "Use a planner.", freshness: "current", provenance: { label: "Researched by Matchgoer", source_url: null, last_checked: "2026-08-21" } },
      ] },
      { key: "tickets_entry", label: "Tickets & entry", facts: [
        { topic: "Buy online", content: "Check this fixture.", freshness: "current", provenance: { label: "Official", source_url: "https://tickets.example.com", last_checked: "2026-08-21" } },
        { topic: "Matchday ticket offices", content: "Long sourced ticket-office answer.", freshness: "current", provenance: { label: "Official", source_url: "https://example.com/tickets", last_checked: "2026-08-21" } },
        { topic: "Safety instructions", content: "Follow instructions.", freshness: "current", provenance: { label: "Official", source_url: null, last_checked: "2026-08-21" } },
      ] },
      { key: "at_ground", label: "At the ground", facts: [
        { topic: "Accessible entrance", content: "Use the accessible entrance.", freshness: "current", provenance: { label: "Official", source_url: "https://example.com/access", last_checked: "2026-08-21" } },
        { topic: "Food and drink", content: "Catering is available.", freshness: "current", provenance: { label: "Official", source_url: "https://example.com/food", last_checked: "2026-08-21" } },
        { topic: "Deposit", content: "A deposit is available.", freshness: "current", provenance: { label: "Official", source_url: "https://example.com/deposit", last_checked: "2026-08-21" } },
      ] },
      { key: "getting_back", label: "Getting back", facts: [
        { topic: "Return toward central Kraków", content: "Check live travel.", freshness: "current", provenance: { label: "Researched by Matchgoer", source_url: null, last_checked: "2026-08-21" } },
      ] },
    ],
  };

  assert.deepEqual(primaryGuideSections(hutnikGuide).map((section) => [section.key, section.facts.map((fact) => fact.topic)]), [
    ["tickets_entry", ["Buy online", "Matchday ticket offices"]],
    ["at_ground", ["Accessible entrance"]],
  ]);
  assert.deepEqual(secondaryGuideSections(hutnikGuide).map((section) => [section.key, section.facts.map((fact) => fact.topic)]), [
    ["getting_there", ["Nearest tram stop", "Bus alternatives", "From central Kraków"]],
    ["at_ground", ["Food and drink", "Deposit"]],
    ["getting_back", ["Return toward central Kraków"]],
  ]);
  assert.equal(officialTicketUrl(hutnikGuide), "https://tickets.example.com");
  assert.deepEqual(fixtureGuideActions(hutnikGuide, 22950), [
    { label: "Directions", href: "/venue/22950#directions", external: false },
    { label: "Tickets", href: "https://tickets.example.com", external: true },
    { label: "Ground guide", href: "/venue/22950#venue-guide-heading", external: false },
  ]);
  assert.equal(primaryGuideSections(hutnikGuide).some((section) => section.key === "before_match"), false);
  assert.equal(primaryGuideSections(hutnikGuide)[0].facts[0].provenance.label, "Official");
  assert.equal(supporterFacingFactContent(primaryGuideSections(hutnikGuide)[0].facts[1]), "Tickets are normally available at the stadium ticket offices from one hour before kick-off. Check the fixture announcement for exceptions.");
});

test("ticket action requires a current official source", () => {
  const staleGuide = guide("expired");
  staleGuide.sections[0].key = "tickets_entry";
  staleGuide.sections[0].facts[0].topic = "Buy online";
  staleGuide.sections[0].facts[0].provenance = { label: "Official", source_url: "https://tickets.example.com", last_checked: "2026-08-21" };
  assert.equal(officialTicketUrl(staleGuide), null);
  staleGuide.sections[0].facts[0].freshness = "needs_review";
  assert.equal(officialTicketUrl(staleGuide), null);
});

test("a venue without guide facts remains empty and graceful", () => {
  const emptyGuide: VenueGuide = { venue_id: 1, has_current_information: false, sections: [] };
  assert.deepEqual(primaryGuideSections(emptyGuide), []);
  assert.deepEqual(secondaryGuideSections(emptyGuide), []);
  assert.equal(officialTicketUrl(emptyGuide), null);
  assert.deepEqual(ticketPresentation(emptyGuide), { facts: [], url: null, unknownMessage: "Ticket information not yet confirmed." });
  assert.equal(guideSummary(emptyGuide), null);
});
