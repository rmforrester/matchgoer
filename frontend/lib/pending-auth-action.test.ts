import assert from "node:assert/strict";
import test from "node:test";

import {
  PENDING_ACTION_MAX_AGE_MS,
  WHOS_GOING_ENABLE,
  parsePendingWhosGoingAction,
  pendingWhosGoingReturnTo,
} from "./pending-auth-action.ts";
import {
  applyPendingWhosGoing,
  prepareSigninConversion,
  clearConversionHandoff,
  clearPendingWhosGoing,
  loadConversionHandoff,
  loadPendingWhosGoing,
  saveConversionHandoff,
  savePendingWhosGoingFromReturnTo,
  type BrowserStorage,
} from "./account-conversion-checkpoint.ts";

function memoryStorage(): BrowserStorage {
  const values = new Map<string, string>();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value); },
    removeItem: (key) => { values.delete(key); },
  };
}

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

test("persists an expiring handoff and pending action outside the confirmation URL", () => {
  const target = memoryStorage();
  const now = 1_800_000_000_000;
  const returnTo = pendingWhosGoingReturnTo(12345, now);
  saveConversionHandoff({ token: "x".repeat(43), expiresAt: new Date(now + 60_000).toISOString(), returnTo }, target);
  savePendingWhosGoingFromReturnTo(returnTo, now, target);
  assert.equal(loadConversionHandoff(now, target)?.returnTo, returnTo);
  assert.equal(loadPendingWhosGoing(12345, now, target)?.fixtureId, 12345);
  clearConversionHandoff(target);
  clearPendingWhosGoing(target);
  assert.equal(loadConversionHandoff(now, target), null);
  assert.equal(loadPendingWhosGoing(12345, now, target), null);
});

test("expired handoff and mismatched pending action fail closed", () => {
  const target = memoryStorage();
  const now = 1_800_000_000_000;
  saveConversionHandoff({ token: "x".repeat(43), expiresAt: new Date(now - 1).toISOString(), returnTo: "/fixture/9" }, target);
  savePendingWhosGoingFromReturnTo(pendingWhosGoingReturnTo(9, now), now, target);
  assert.equal(loadConversionHandoff(now, target), null);
  assert.equal(loadPendingWhosGoing(10, now, target), null);
});

test("applies Who's Going once and verifies authoritative Interested state", async () => {
  let puts = 0;
  let reads = 0;
  const pending = { action: WHOS_GOING_ENABLE, fixtureId: 9, issuedAt: Date.now() } as const;
  const result = await applyPendingWhosGoing(
    pending,
    async (fixtureId) => { puts += 1; assert.equal(fixtureId, 9); return { interested: true, open_to_meet: true }; },
    async () => { reads += 1; return { interested: true, open_to_meet: true }; },
  );
  assert.deepEqual(result, { interested: true, open_to_meet: true });
  assert.equal(puts, 1);
  assert.equal(reads, 1);
});



test("native sign-in keeps the current destination without changing the transfer credential", async () => {
  const previous = process.env.NEXT_PUBLIC_NATIVE_AUTH;
  try {
    for (const native of ["true", "false"]) {
      process.env.NEXT_PUBLIC_NATIVE_AUTH = native;
      for (const handoffToken of [undefined, "e".repeat(40)]) {
        const target = memoryStorage();
        const original = { token: "h".repeat(40), expiresAt: "2099-01-01T00:00:00Z", returnTo: "/account" };
        saveConversionHandoff(original, target);
        const actual = await prepareSigninConversion("/my-football?tab=visited", false, handoffToken, target, {
          getAnonymousSession: async () => { throw new Error("Must reuse existing checkpoint"); },
          issueHandoff: async () => { throw new Error("Must not replace the transfer credential"); },
        });
        assert.deepEqual(actual, { ...original, returnTo: native === "true" ? "/my-football?tab=visited" : "/account" });
        assert.deepEqual(loadConversionHandoff(Date.now(), target), actual);
      }
    }
  } finally {
    if (previous === undefined) delete process.env.NEXT_PUBLIC_NATIVE_AUTH;
    else process.env.NEXT_PUBLIC_NATIVE_AUTH = previous;
  }
});
