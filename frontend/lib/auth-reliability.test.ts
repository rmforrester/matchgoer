import test from "node:test";
import assert from "node:assert/strict";
import axios from "axios";
import type { SupabaseClient } from "@supabase/supabase-js";
import api, { anonymousApi } from "./api.ts";
import { accountIssue, confirmationLinkError, emailRateLimited, logout, recoveryRedirect, rememberedRecovery, rememberRecovery, requestPasswordRecovery, updatePassword } from "./auth-reliability.ts";

test("recovery uses only provider calls, an isolated route and safe intended destination", async () => {
  const previous = api.defaults.adapter; const anonymousPrevious = anonymousApi.defaults.adapter;
  api.defaults.adapter = anonymousApi.defaults.adapter = async () => { throw new Error("Recovery must never call account claim or guest session"); };
  const calls: unknown[] = [];
  const client = { auth: { resetPasswordForEmail: async (...args: unknown[]) => { calls.push(args); return { error: null }; }, updateUser: async (arg: unknown) => { calls.push(arg); return { error: null }; } } } as unknown as SupabaseClient;
  try {
    await requestPasswordRecovery(client, " synthetic@example.test ", "https://beta.matchgoer.com", "/my-football?tab=interested");
    await updatePassword(client, "SyntheticPassword123!");
    assert.deepEqual(calls, [["synthetic@example.test", { redirectTo: "https://beta.matchgoer.com/auth/recovery?returnTo=%2Fmy-football%3Ftab%3Dinterested" }], { password: "SyntheticPassword123!" }]);
    assert.equal(recoveryRedirect("https://beta.matchgoer.com", "//untrusted.test"), "https://beta.matchgoer.com/auth/recovery?returnTo=%2Faccount");
  } finally { api.defaults.adapter = previous; anonymousApi.defaults.adapter = anonymousPrevious; }
});

test("provider password/update/logout failures reject rather than reporting success", async () => {
  const error = new Error("Synthetic provider failure");
  const client = { auth: { resetPasswordForEmail: async () => ({ error }), updateUser: async () => ({ error }), signOut: async () => ({ error }) } } as unknown as SupabaseClient;
  await assert.rejects(requestPasswordRecovery(client, "synthetic@example.test", "https://beta.matchgoer.com"), error);
  await assert.rejects(updatePassword(client, "SyntheticPassword123!"), error);
  await assert.rejects(logout(client), error);
  await assert.rejects(logout(null));
});

test("session expiry, temporary API failure and unlinked identity are distinguished", () => {
  const request = (status: number, code: string) => new axios.AxiosError("Synthetic", "ERR", undefined, undefined, { status, statusText: "", headers: {}, config: { headers: {} } as never, data: { detail: { code } } });
  assert.equal(accountIssue(request(401, "TOKEN_EXPIRED")), "expired");
  assert.equal(accountIssue(request(503, "")), "unavailable");
  assert.equal(accountIssue(new axios.AxiosError("offline")), "unavailable");
  assert.equal(accountIssue(request(403, "IDENTITY_NOT_LINKED")), "unlinked");
  assert.equal(accountIssue({ code: "refresh_token_not_found" }), "expired");
});

test("expired confirmation and throttled email errors are recognised without raw error rendering", () => {
  assert.equal(confirmationLinkError({ code: "otp_expired" }), true);
  assert.equal(confirmationLinkError(new Error("Token has expired or is invalid")), true);
  assert.equal(confirmationLinkError(new Error("offline")), false);
  assert.equal(emailRateLimited({ status: 429 }), true);
});

test("recovery continuity is scoped to the verified owner and can be cleared", () => {
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: { getItem: (k: string) => values.get(k) ?? null, setItem: (k: string, v: string) => values.set(k, v), removeItem: (k: string) => values.delete(k) } });
  try {
    assert.equal(rememberedRecovery("synthetic-owner"), false);
    rememberRecovery("synthetic-owner");
    assert.equal(rememberedRecovery("synthetic-owner"), true);
    assert.equal(rememberedRecovery("different-owner"), false);
    rememberRecovery(null);
    assert.equal(rememberedRecovery("synthetic-owner"), false);
  } finally { Reflect.deleteProperty(globalThis, "sessionStorage"); }
});
