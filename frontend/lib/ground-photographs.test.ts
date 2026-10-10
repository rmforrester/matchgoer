import test from "node:test";
import assert from "node:assert/strict";
import { groundPhotograph } from "./ground-photographs.ts";

test("reviewed pilot uses canonical IDs, never provider or loose-name fallback", () => {
  const ids = [3535, 581, 22820, 6189, 553, 556, 23286, 1833];
  for (const id of ids) {
    const photo = groundPhotograph(id);
    assert.ok(photo);
    assert.equal(photo.venueId, id);
    assert.match(photo.src, /^https:\/\/thumb\.wikimedia\.org\/wikipedia\/commons\/thumb\//);
    assert.match(photo.sourceUrl, /^https:\/\/commons\.wikimedia\.org\/wiki\/File:/);
    assert.match(photo.licenseUrl, /^https?:\/\/creativecommons\.org\//);
    assert.ok(photo.credit && photo.captureDate && photo.alt);
    assert.ok(photo.width > 0 && photo.height > 0);
  }
  for (const id of [535, 568, 1506, 20470, 999999]) assert.equal(groundPhotograph(id), undefined);
});
