import assert from "node:assert/strict";
import test from "node:test";

import api, { anonymousApi } from "./api.ts";
import { authCallbackRoute, completeAuthenticatedFlow, signinRoute } from "./auth-flow.ts";
import {
  clearConversionHandoffAfter,
  loadConversionHandoff,
  prepareConversionHandoff,
  prepareSigninConversion,
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
  assert.equal(new URL(signinRoute("/fixture/42", null, true), "https://matchgoer.test").searchParams.get("convert"), "1");
});

test("prepares and stores a server-issued handoff before conversion sign-in", async () => {
  const target = memoryStorage();
  const previous = anonymousApi.defaults.adapter;
  anonymousApi.defaults.adapter = async (config) => ({
    data: { handoff_token: "h".repeat(40), expires_at: "2099-01-01T00:00:00Z" },
    status: 200, statusText: "OK", headers: {}, config,
  });
  try {
    const handoff = await prepareConversionHandoff("/fixture/42", target);
    assert.equal(handoff.token, "h".repeat(40));
    assert.equal(loadConversionHandoff(Date.now(), target)?.returnTo, "/fixture/42");
  } finally {
    anonymousApi.defaults.adapter = previous;
  }
});

test("anonymous Interested to existing-account sign-in replaces a stale checkpoint and claims the current handoff", async () => {
  const target = memoryStorage();
  saveConversionHandoff({ token: "s".repeat(40), expiresAt: "2099-01-01T00:00:00Z", returnTo: "/fixture/7" }, target);
  const issued: string[] = [];
  const checkpoint = await prepareSigninConversion(
    "/fixture/42",
    true,
    null,
    target,
    {
      getAnonymousSession: async () => ({ anonymous: true, anonymous_activity: true }),
      issueHandoff: async (returnTo, storage) => {
        issued.push(returnTo);
        const fresh = { token: "f".repeat(40), expiresAt: "2099-01-01T00:00:00Z", returnTo };
        saveConversionHandoff(fresh, storage);
        return fresh;
      },
    },
  );

  const requests: Array<{ method?: string; url?: string; data?: string }> = [];
  const previous = api.defaults.adapter;
  api.defaults.adapter = async (config) => {
    requests.push({ method: config.method, url: config.url, data: config.data });
    return {
      data: config.url === "/session" ? { anonymous: false } : { profile_complete: true },
      status: 200, statusText: "OK", headers: {}, config,
    };
  };
  try {
    const destination = await completeAuthenticatedFlow(
      { access_token: "existing-account-token" } as never,
      checkpoint?.returnTo,
      checkpoint?.token,
    );
    assert.deepEqual(issued, ["/fixture/42"]);
    assert.equal(loadConversionHandoff(Date.now(), target)?.token, "f".repeat(40));
    assert.equal(destination.kind, "ready");
    assert.equal(destination.route, "/account/ready?returnTo=%2Ffixture%2F42");
    assert.match(requests[1].data ?? "", new RegExp("f{40}"));
    assert.doesNotMatch(requests[1].data ?? "", new RegExp("s{40}"));
  } finally {
    api.defaults.adapter = previous;
  }
});

test("explicit callback handoff is never replaced by local conversion preparation", async () => {
  const target = memoryStorage();
  saveConversionHandoff({ token: "s".repeat(40), expiresAt: "2099-01-01T00:00:00Z", returnTo: "/fixture/7" }, target);
  let sessionRequests = 0;
  let handoffsIssued = 0;
  await prepareSigninConversion("/fixture/42", true, "callback-token", target, {
    getAnonymousSession: async () => { sessionRequests += 1; return { anonymous: true, anonymous_activity: true }; },
    issueHandoff: async () => { handoffsIssued += 1; throw new Error("must not issue"); },
  });
  assert.equal(sessionRequests, 0);
  assert.equal(handoffsIssued, 0);
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
