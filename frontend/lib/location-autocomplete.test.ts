import { test } from "node:test";
import assert from "node:assert/strict";
import { autocompleteParameters, locationSuggestions, EUROPE_LOCATION_BIAS, AUTOCOMPLETE_DELAY } from "./location-autocomplete.ts";

test("debounced provider contract retains audited preference without restrictive filters", () => {
  assert.equal(AUTOCOMPLETE_DELAY, 275);
  for (const q of ["", " ", "s", " s "]) assert.equal(autocompleteParameters(q), null);
  const p = autocompleteParameters(" stock ")!;
  assert.equal(p.get("text"), "stock");
  assert.equal(p.get("bias"), EUROPE_LOCATION_BIAS);
  assert.equal(p.get("limit"), "6");
  assert.equal(p.get("type"), "city");
  assert.equal(p.has("filter"), false);
  assert.equal(p.has("apiKey"), false);
});
test("labels use structured names, preserve US results and provider ordering", () => {
  const items = locationSuggestions({ results: [
    { city: "Southampton", state: "England", country: "United Kingdom", formatted: "yes, Southampton", lat: 50.9, lon: -1.4 },
    { city: "Southampton", state: "New York", country: "United States", lat: 40.8, lon: -72.3 },
  ] });
  assert.deepEqual(items.map(x => x.label), ["Southampton, England, United Kingdom", "Southampton, New York, United States"]);
});
test("deduplicate only exact identifiers or exact named coordinates", () => {
  const a = { city: "Stockholm", country: "Sweden", lat: 59.3, lon: 18.1, place_id: "one" };
  const items = locationSuggestions({ results: [a, a, { ...a, place_id: "two" }, { ...a, city: "Stockholm Municipality", place_id: "three" }, { ...a, lat: 60, place_id: "four" }] });
  assert.equal(items.length, 3);
  assert.equal(items[1].name, "Stockholm Municipality");
});
test("reject invalid coordinates and malformed payloads; cap visible results", () => {
  for (const p of [null, {}, { results: "bad" }]) assert.deepEqual(locationSuggestions(p), []);
  assert.deepEqual(locationSuggestions({ results: [null, { city: "Bad", country: "X", lat: 100, lon: 0 }, { city: "Bad", country: "X", lat: "1", lon: 1 }] }), []);
  assert.equal(locationSuggestions({ results: Array.from({ length: 9 }, (_, i) => ({ name: `Town ${i}`, country: "Country", lat: i, lon: i })) }).length, 6);
});
