import assert from "node:assert/strict";
import test from "node:test";
import { refreshFailure, uploadFeedback, uncertainPhotoResponse } from "./terraces-feedback.ts";
test("whole-batch success only when every selected photo is confirmed", () => {
  assert.equal(uploadFeedback(3,3,"").kind,"success");
  assert.equal(uploadFeedback(0,3,"That didn't work. Give it another go.").text,"That didn't work. Give it another go.");
  assert.equal(uploadFeedback(0,3,"failure").kind,"error");
});
test("partial success has one truthful outcome and remaining count", () => {
  assert.deepEqual(uploadFeedback(2,3,"failure"),{kind:"error",text:"2 photos sent. One didn't go through — try again."});
  assert.match(uploadFeedback(1,3,"failure").text,/1 photo sent. 2 still/);
});
test("failed refresh preserves confirmed persistence without calling submission failed", () => {
  const outcome=refreshFailure(uploadFeedback(3,3,""));
  assert.equal(outcome.kind,"error");assert.match(outcome.text,/Photos sent/);assert.match(outcome.text,/Can't load/);
  assert.doesNotMatch(outcome.text,/didn't work/);
  assert.equal(refreshFailure().text,"Can't connect right now. Try again in a moment.");
});
test("idempotent retry of already reviewed photos does not promise another review", () => {
  assert.equal(uploadFeedback(1,1,"",true).text,"Your photos are saved.");
});
test("lost/503 responses do not claim the server definitely rejected a photo", () => {
  assert.equal(uncertainPhotoResponse(new Error("timeout")),true);
  assert.equal(uncertainPhotoResponse({response:{status:503}}),true);
  assert.equal(uncertainPhotoResponse({response:{status:422}}),false);
  assert.equal(uploadFeedback(2,3,"",false,true).text,"2 photos sent. We couldn't confirm one — try again.");
});
