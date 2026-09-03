import assert from "node:assert/strict";
import test from "node:test";

import api from "./api.ts";
import { authCallbackRoute, completeAuthenticatedFlow, prepareSigninConversion, signinRoute } from "./auth-flow.ts";
import {
  clearConversionHandoffAfter,
  loadConversionHandoff,
  saveConversionHandoff,
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

test("registered session still claims when a conversion handoff exists", async () => {
  const requests: Array<{ method?: string; url?: string; data?: string }> = [];
  const previous = api.defaults.adapter;
  api.defaults.adapter = async (config) => {
    requests.push({ method: config.method, url: config.url, data: config.data });
    const data = config.url === "/session"
      ? { anonymous: false }
      : { profile_complete: true };
    return { data, status: 200, statusText: "OK", headers: {}, config };
  };
  try {
    const result = await completeAuthenticatedFlow({ access_token: "provider-token" } as never, "/fixture/42", "opaque-handoff-token");
    assert.equal(result.kind, "ready");
    assert.deepEqual(requests.map(({ method, url }) => [method, url]), [["get", "/session"], ["post", "/account/claim"]]);
    assert.match(requests[1].data ?? "", /opaque-handoff-token/);
  } finally {
    api.defaults.adapter = previous;
  }
});

test("callback route carries only the opaque handoff and allowlisted return path", () => {
  const route = new URL(authCallbackRoute("https://evil.example/steal", "opaque-token"), "https://matchgoer.test");
  assert.equal(route.pathname, "/auth/callback");
  assert.equal(route.searchParams.get("handoff"), "opaque-token");
  assert.equal(route.searchParams.get("returnTo"), "/my-football?tab=interested");
  assert.equal(route.searchParams.has("user_id"), false);
  assert.equal(new URL(signinRoute("/fixture/42", "opaque-token"), "https://matchgoer.test").searchParams.get("handoff"), "opaque-token");
});

test("successful conversion clears checkpoint while retryable failure preserves it", async () => {
  const target = memoryStorage();
  const checkpoint = { token: "x".repeat(40), expiresAt: "2099-01-01T00:00:00Z", returnTo: "/fixture/42" };
  saveConversionHandoff(checkpoint, target);
  await assert.rejects(clearConversionHandoffAfter(Promise.reject(new Error("retry")), target));
  assert.equal(loadConversionHandoff(Date.now(), target)?.token, checkpoint.token);
  assert.equal(await clearConversionHandoffAfter(Promise.resolve("done"), target), "done");
  assert.equal(loadConversionHandoff(Date.now(), target), null);
});

test("header sign in creates a handoff only for meaningful anonymous activity", async () => {
  const saved: Array<{ token: string; expiresAt: string; returnTo: string }> = [];
  let issues = 0;
  const dependencies = (state: { anonymous: boolean; anonymous_activity: boolean }) => ({
    readSession: async () => state,
    issueHandoff: async () => {
      issues += 1;
      return { handoff_token: "h".repeat(40), expires_at: "2099-01-01T00:00:00Z" };
    },
    saveHandoff: (value: { token: string; expiresAt: string; returnTo: string }) => { saved.push(value); },
  });

  assert.equal(await prepareSigninConversion("/fixture/42", dependencies({ anonymous: true, anonymous_activity: false })), null);
  assert.equal(await prepareSigninConversion("/fixture/42", dependencies({ anonymous: false, anonymous_activity: true })), null);
  assert.equal(await prepareSigninConversion("/fixture/42", dependencies({ anonymous: true, anonymous_activity: true })), "h".repeat(40));
  assert.equal(issues, 1);
  assert.deepEqual(saved, [{ token: "h".repeat(40), expiresAt: "2099-01-01T00:00:00Z", returnTo: "/fixture/42" }]);
});
