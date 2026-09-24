import assert from "node:assert/strict";
import test from "node:test";
import { fixtureGuideActions, googleMapsDirectionsUrl, guideSummary, isExceptionalTicketGuidance, officialTicketUrl, primaryGuideSections, secondaryGuideSections, shouldShowTicketFact, supporterFacingFactContent, supporterFacingFactTopic, ticketPresentation, type VenueGuide, type VenueGuideFact } from "./venue-guide.ts";

const guide = (freshness: "current" | "needs_review" | "expired"): VenueGuide => ({
  venue_id: 22950,
  club_venue_id: null,
  club_name: null,
  has_current_information: freshness === "current",
  before_match: [],
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
    club_venue_id: null,
    club_name: null,
    has_current_information: true,
    before_match: [],
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
    ["tickets_entry", ["Matchday ticket offices"]],
    ["at_ground", ["Accessible entrance"]],
  ]);
  assert.deepEqual(secondaryGuideSections(hutnikGuide).map((section) => [section.key, section.facts.map((fact) => fact.topic)]), [
    ["getting_there", ["Nearest tram stop", "Bus alternatives", "From central Kraków"]],
    ["at_ground", ["Food and drink", "Deposit"]],
    ["getting_back", ["Return toward central Kraków"]],
  ]);
  assert.equal(officialTicketUrl(hutnikGuide), "https://tickets.example.com");
  const actions = fixtureGuideActions(hutnikGuide, 22950, { latitude: 50.066111, longitude: 20.057222 });
  assert.deepEqual(actions, [
    { label: "Directions", href: "https://www.google.com/maps/dir/?api=1&destination=50.066111%2C20.057222", external: true },
    { label: "Tickets", href: "https://tickets.example.com", external: true },
    { label: "Ground guide", href: "/venue/22950#venue-guide-heading", external: false },
  ]);
  const directions = new URL(actions[0].href, "https://matchgoer.app");
  assert.equal(directions.searchParams.get("destination"), "50.066111,20.057222");
  assert.equal(directions.searchParams.has("origin"), false);
  assert.equal(primaryGuideSections(hutnikGuide).some((section) => section.key === "before_match"), false);
  assert.equal(primaryGuideSections(hutnikGuide)[0].facts[0].provenance.label, "Official");
  assert.equal(supporterFacingFactContent(primaryGuideSections(hutnikGuide)[0].facts[0]), "Tickets are normally available at the stadium ticket offices from one hour before kick-off. Check the fixture announcement for exceptions.");
});

test("routine ticket prose is hidden while its canonical fixture action survives", () => {
  const routine = guide("current");
  routine.sections[0] = {
    key: "tickets_entry",
    label: "Tickets & entry",
    facts: [
      { topic: "Tickets", content: "Club match tickets.", freshness: "current", provenance: { label: "Official", source_url: "https://tickets.example.com", last_checked: "2026-09-24" } },
      { topic: "official_ticket_portal", content: "Buy from the official portal.", freshness: "current", provenance: { label: "Official", source_url: "https://tickets.example.com", last_checked: "2026-09-24" } },
      { topic: "entry", content: "Use the turnstile on the ticket.", freshness: "current", provenance: { label: "Official", source_url: "https://entry.example.com", last_checked: "2026-09-24" } },
    ],
  };
  assert.deepEqual(primaryGuideSections(routine)[0].facts.map((fact) => fact.topic), ["entry"]);
  assert.equal(officialTicketUrl(routine), "https://tickets.example.com");
  assert.equal(fixtureGuideActions(routine, 1, null)[0].label, "Tickets");
});

test("broad ticket topics retain non-obvious purchase and entry exceptions", () => {
  const examples = [
    "Cash-only sales are available at the gate.",
    "There are no ticket sales at the turnstiles.",
    "Collect tickets from the ticket office.",
    "Home tickets are allocated to members by ballot.",
    "Concession tickets must be bought from the office.",
    "Under-16 tickets must be bought with an adult ticket.",
    "Disabled supporters and carers use the accessible ticket process.",
    "Screenshots of digital tickets are not accepted.",
    "Away tickets are restricted to the visiting allocation.",
    "Pay-on-entry is limited to designated Popside turnstiles.",
    "A separate transport ticket must be generated online.",
  ];
  for (const content of examples) {
    const fact: VenueGuideFact = { topic: "tickets", content, freshness: "current", provenance: { label: "Official", source_url: "https://tickets.example.com", last_checked: "2026-09-24" } };
    assert.equal(isExceptionalTicketGuidance(fact), true, content);
    assert.equal(shouldShowTicketFact(fact), true, content);
  }
  const routine: VenueGuideFact = { topic: "tickets", content: "Use the official website to buy match tickets.", freshness: "current", provenance: { label: "Official", source_url: "https://tickets.example.com", last_checked: "2026-09-24" } };
  assert.equal(isExceptionalTicketGuidance(routine), false);
  assert.equal(shouldShowTicketFact(routine), false);
});

test("all currently serving broad-topic exceptions survive the presentation filter", () => {
  const currentExceptions = [
    ["general_purchase_process", "Home general admission is primarily member-based and high-demand fixtures may use ballots; check the official fixture sale and Ticket Exchange."],
    ["official_ticket_portal", "Men's home-match tickets are generally sold through membership sales and ballots."],
    ["general_purchase_process", "Buy an e-ticket in advance or use the Plainmoor ticket office. Pay-on-entry by card is limited to designated Popside turnstiles."],
    ["tickets", "Men's Bundesliga home day tickets are generally allocated to members by ballot; use Union's official ticket shop and resale route."],
    ["tickets", "Use HSV's official ticket shop. A separate free HVV KombiTicket must be generated online for public transport."],
  ];
  for (const [topic, content] of currentExceptions) {
    const fact: VenueGuideFact = { topic, content, freshness: "current", provenance: { label: "Official", source_url: "https://tickets.example.com", last_checked: "2026-09-24" } };
    assert.equal(shouldShowTicketFact(fact), true, `${topic}: ${content}`);
  }
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
  const emptyGuide: VenueGuide = { venue_id: 1, club_venue_id: null, club_name: null, has_current_information: false, sections: [], before_match: [] };
  assert.deepEqual(primaryGuideSections(emptyGuide), []);
  assert.deepEqual(secondaryGuideSections(emptyGuide), []);
  assert.equal(officialTicketUrl(emptyGuide), null);
  assert.deepEqual(ticketPresentation(emptyGuide), { facts: [], url: null, unknownMessage: "Ticket information not yet confirmed." });
  assert.equal(guideSummary(emptyGuide), null);
});

test("fixture actions omit directions when canonical venue coordinates are unavailable", () => {
  const ticketGuide = guide("current");
  ticketGuide.sections[0].key = "tickets_entry";
  ticketGuide.sections[0].facts[0].topic = "Buy online";
  ticketGuide.sections[0].facts[0].provenance = { label: "Official", source_url: "https://tickets.example.com", last_checked: "2026-08-21" };
  assert.deepEqual(fixtureGuideActions(ticketGuide, 22950, { latitude: null, longitude: 20.057222 }), [
    { label: "Tickets", href: "https://tickets.example.com", external: true },
    { label: "Ground guide", href: "/venue/22950#venue-guide-heading", external: false },
  ]);
  assert.deepEqual(fixtureGuideActions(ticketGuide, 22950, null), [
    { label: "Tickets", href: "https://tickets.example.com", external: true },
    { label: "Ground guide", href: "/venue/22950#venue-guide-heading", external: false },
  ]);
});

test("fixture guide context is explicit, shareable, and keeps the gateway compact", () => {
  const contextual = guide("current");
  contextual.club_venue_id = 10;
  contextual.sections[0].key = "tickets_entry";
  contextual.sections[0].facts[0].topic = "official_ticket_portal";
  contextual.sections[0].facts[0].provenance = { label: "Official", source_url: "https://tickets.example.com", last_checked: "2026-08-26" };
  contextual.before_match = [{
    pre_match_spot_id: 1,
    display_name: "The Supporters Pub",
    classification: "SUPPORTER_SPOT",
    audience: "HOME",
    supporting_line: "Popular with home fans before matches.",
    location_context: null,
    directions_url: "https://www.google.com/maps/search/?api=1&query=The+Supporters+Pub",
  }];
  const actions = fixtureGuideActions(contextual, 494, { latitude: 51.5, longitude: -0.1 }, 42);
  assert.equal(actions.length, 3);
  assert.equal(actions[1].href, "https://tickets.example.com");
  assert.equal(actions[2].href, "/venue/494?teamId=42#venue-guide-heading");
  assert.equal(contextual.before_match[0].classification, "SUPPORTER_SPOT");
  assert.equal(supporterFacingFactTopic(contextual.sections[0].facts[0]), "Tickets");
});
