import assert from "node:assert/strict";
import test from "node:test";

import {
  PENDING_ACTION_MAX_AGE_MS,
  WHOS_GOING_ENABLE,
  parsePendingWhosGoingAction,
  pendingWhosGoingReturnTo,
} from "./pending-auth-action.ts";

test("builds and parses the single allowlisted pending action", () => {
  const now = 1_800_000_000_000;
  const returnTo = pendingWhosGoingReturnTo(12345, now);
  const url = new URL(returnTo, "https://beta.matchgoer.com");
  assert.equal(url.pathname, "/fixture/12345");
  assert.deepEqual(parsePendingWhosGoingAction(url.searchParams, 12345, now), {
    action: WHOS_GOING_ENABLE, fixtureId: 12345, issuedAt: now,
  });
});

test("rejects arbitrary actions, invalid or mismatched fixtures, and expired intent", () => {
  const now = 1_800_000_000_000;
  const valid = new URL(pendingWhosGoingReturnTo(9, now), "https://beta.matchgoer.com");
  valid.searchParams.set("pendingAction", "delete-everything");
  assert.equal(parsePendingWhosGoingAction(valid.searchParams, 9, now), null);

  const mismatched = new URL(pendingWhosGoingReturnTo(9, now), "https://beta.matchgoer.com");
  assert.equal(parsePendingWhosGoingAction(mismatched.searchParams, 10, now), null);
  mismatched.searchParams.set("pendingFixtureId", "../9");
  assert.equal(parsePendingWhosGoingAction(mismatched.searchParams, 9, now), null);

  const expired = new URL(pendingWhosGoingReturnTo(9, now - PENDING_ACTION_MAX_AGE_MS - 1), "https://beta.matchgoer.com");
  assert.equal(parsePendingWhosGoingAction(expired.searchParams, 9, now), null);
});

test("rejects invalid fixture ids when creating intent", () => {
  assert.throws(() => pendingWhosGoingReturnTo(0));
  assert.throws(() => pendingWhosGoingReturnTo(Number.NaN));
});

