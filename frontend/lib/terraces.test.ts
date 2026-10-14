import assert from "node:assert/strict";
import test from "node:test";
import { occupiedPhotoSlots, photoMetadata, recordedPhotoAttendance, terracesError, validatePhotoSelection, type TerracePhoto } from "./terraces.ts";
import type { MyGround } from "../app/types/grounds.ts";

const file = { size: 40, type: "image/jpeg", name: "photo.jpg" };
test("three active slots, including incomplete reservations; rejected/removed release slots", () => {
  assert.equal(occupiedPhotoSlots([{ status: "PENDING", upload_state: "incomplete" }, { status: "APPROVED" }, { status: "REJECTED" }, { status: "REMOVED" }] as TerracePhoto[]), 2);
  assert.equal(validatePhotoSelection([file], 2), null);
  assert.match(validatePhotoSelection([file, file], 2)!, /three/);
});
test("exact 10MB byte limit and supported formats; never silently relabel arbitrary files", () => {
  for (const type of ["image/jpeg", "image/png", "image/heic", "image/heif"]) assert.equal(validatePhotoSelection([{ ...file, type, size: 10_000_000 }], 0), null);
  assert.equal(validatePhotoSelection([{ ...file, type: "", name: "IMG.HEIC" }], 0), null);
  assert.match(validatePhotoSelection([{ ...file, size: 10_000_001 }], 0)!, /10 MB/);
  assert.match(validatePhotoSelection([{ ...file, size: 0 }], 0)!, /10 MB/);
  assert.match(validatePhotoSelection([{ ...file, type: "image/svg+xml" }], 0)!, /JPEG/);
  assert.match(validatePhotoSelection([], 0)!, /Choose/);
});
test("B1 metadata is base64url UTF-8 with explicit consent/rights and no identity fields", () => {
  const value=photoMetadata("Göteborg’s football ⚽", true);
  assert.match(value, /^[a-zA-Z0-9_-]+$/);
  assert.deepEqual(JSON.parse(Buffer.from(value, "base64url").toString("utf8")), { caption: "Göteborg’s football ⚽", public_consent: true, rights_acknowledged: true, consent_version: "terraces-public-v1" });
  assert.throws(() => photoMetadata("hello", false));
  assert.throws(() => photoMetadata("x".repeat(201), true));
});
test("recorded canonical visits retain separate repeat visits and unknown historical context", () => {
  const ground={ venue_id: 9, venue_name: "Canonical ground", visits: [{ visit_id: 1, fixture_id: null, visit_date: null }, { visit_id: 2, fixture_id: 50, visit_date: "2026-10-01" }, { visit_id: 3, fixture_id: 50, visit_date: "2026-10-01" }], attended_fixtures: [{ fixture_id: 50, home_team: "Home", away_team: "Away" }] } as MyGround;
  const before=JSON.stringify(ground); const rows=recordedPhotoAttendance([ground]);
  assert.deepEqual(rows.map(row => row.visit_id), [1,2,3]); assert.equal(rows[0].home_team,null); assert.equal(rows[0].match_date,null); assert.equal(rows[1].venue_id,9); assert.equal(JSON.stringify(ground),before);
  assert.deepEqual(recordedPhotoAttendance([]),[]);
});
test("disabled, forbidden and failed actions have safe, honest error copy", () => {
  for(const status of [401,403]) assert.match(terracesError({response:{status}}),/verified/);
  assert.match(terracesError({response:{status:404}}),/available/);
  assert.match(terracesError({response:{status:429}}),/busy/);
  assert.match(terracesError({response:{status:503}, detail:"secret"}),/connect/);
  assert.doesNotMatch(terracesError({response:{status:503}, detail:"secret"}),/secret/);
});
