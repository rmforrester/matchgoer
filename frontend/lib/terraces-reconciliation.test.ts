import assert from "node:assert/strict";
import test from "node:test";
import { reconcilePhotoDrafts, photoStatus, type PhotoDraft } from "./terraces-reconciliation.ts";
import type { TerracePhoto } from "./terraces.ts";
const draft = (key: string, attempted = true): PhotoDraft => ({file: new File(["synthetic"], "photo.jpg"), caption: "", key, attempted, outcome: attempted ? "uncertain" : undefined});
const photo = (key: string, upload_state: "ready" | "incomplete" = "ready"): TerracePhoto => ({photo_id: 1, submission_key: key, upload_state, status: "PENDING"} as TerracePhoto);
test("lost successful response reconciles by UUID, never filename or caption", () => {
  assert.deepEqual(reconcilePhotoDrafts([draft("sent")], [photo("sent")]), []);
  assert.equal(reconcilePhotoDrafts([draft("other")], [photo("sent")]).length, 1);
});
test("partial batch retains only failed and untouched photos with original UUIDs", () => {
  const remaining = reconcilePhotoDrafts([draft("sent"), draft("failed"), draft("untouched", false)], [photo("sent")]);
  assert.deepEqual(remaining.map(d => d.key), ["failed", "untouched"]);
  assert.equal(remaining[0].outcome, "failed");
  assert.equal(remaining[1].attempted, false);
});
test("incomplete durable reservation is retryable with its existing UUID", () => {
  const [remaining] = reconcilePhotoDrafts([draft("reserved")], [photo("reserved", "incomplete")]);
  assert.equal(remaining.key, "reserved"); assert.equal(remaining.outcome, "failed");
});
test("gallery status never calls an unpublished photo live", () => {
  assert.equal(photoStatus(photo("incomplete", "incomplete")), "Not sent");
  assert.equal(photoStatus({...photo("rejected"), status:"REJECTED"}), "Rejected");
  assert.equal(photoStatus(photo("pending")), "Pending");
  assert.equal(photoStatus({...photo("approved"), status:"APPROVED", published_at:null}), "Approved");
  assert.equal(photoStatus({...photo("live"), status:"APPROVED", published_at:"2026-10-14"}), "Live");
});
