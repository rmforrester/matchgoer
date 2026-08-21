import assert from "node:assert/strict";
import test from "node:test";
import { guideSummary, type VenueGuide } from "./venue-guide.ts";

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
  });
});

test("fixture without guide fails gracefully", () => {
  assert.equal(guideSummary(null), null);
});

test("stale-only guide does not claim current fixture guidance", () => {
  assert.equal(guideSummary(guide("expired")), null);
});
