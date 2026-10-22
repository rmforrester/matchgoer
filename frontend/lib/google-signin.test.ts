import assert from "node:assert/strict";
import test from "node:test";
import { anonymousApi } from "./api.ts";
import { beginGoogleSignin, googleCallbackError, googleSigninEnabled } from "./google-signin.ts";

test("Google is unavailable unless explicitly enabled, including direct initiation", async () => {
  const previous = process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED;
  try {
    for (const value of [undefined, "false", "TRUE", "1"]) {
      if (value === undefined) delete process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED;
      else process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED = value;
      assert.equal(googleSigninEnabled(), false);
      await assert.rejects(beginGoogleSignin({} as never, "https://beta.matchgoer.com"), /not available/);
    }
    process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED = "true";
    assert.equal(googleSigninEnabled(), true);
  } finally {
    if (previous === undefined) delete process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED;
    else process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED = previous;
  }
});

test("OAuth prepares cookie-bound guest transfer before redirect and sends no account/profile fields", async () => {
  const previous = anonymousApi.defaults.adapter;
  const previousFlag = process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED;
  process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED = "true";
  const requests: string[] = [];
  anonymousApi.defaults.adapter = async config => {
    requests.push(`${config.method} ${config.url}`);
    return { data: config.url === "/session" ? { anonymous: true, anonymous_activity: true } : { handoff_token: "s".repeat(40), expires_at: new Date(Date.now() + 60000).toISOString() }, status: 200, statusText: "OK", headers: {}, config };
  };
  try {
    let options: unknown;
    const client = { auth: { signInWithOAuth: async (value: unknown) => { requests.push("oauth"); options = value; return { error: null }; } } };
    await beginGoogleSignin(client as never, "https://beta.matchgoer.com", "/my-football?tab=went");
    assert.deepEqual(requests, ["get /session", "get /session", "post /account/conversion-handoff", "oauth"]);
    const url = new URL("https://beta.matchgoer.com/auth/callback");
    url.searchParams.set("returnTo", "/my-football?tab=went");
    url.searchParams.set("handoff", "s".repeat(40));
    url.searchParams.set("method", "google");
    assert.deepEqual(options, { provider: "google", options: { redirectTo: url.href } });
  } finally {
    anonymousApi.defaults.adapter = previous;
    if (previousFlag === undefined) delete process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED;
    else process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED = previousFlag;
  }
});

test("explicit handoff is preserved, unsafe return paths are rejected and initiation failures propagate", async () => {
  const previousFlag = process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED;
  process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED = "true";
  try {
    const failure = new Error("synthetic provider unavailable");
    const client = { auth: { signInWithOAuth: async (value: { options: { redirectTo: string } }) => {
      const url = new URL(value.options.redirectTo);
      assert.equal(url.origin, "https://beta.matchgoer.com");
      assert.equal(url.searchParams.get("returnTo"), "/my-football?tab=interested");
      assert.equal(url.searchParams.get("handoff"), "s".repeat(40));
      return { error: failure };
    } } };
    await assert.rejects(beginGoogleSignin(client as never, "https://beta.matchgoer.com", "https://untrusted.test", "s".repeat(40)), failure);
  } finally {
    if (previousFlag === undefined) delete process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED;
    else process.env.NEXT_PUBLIC_GOOGLE_SIGNIN_ENABLED = previousFlag;
  }
});

test("cancelled and failed OAuth use safe messages without reflecting provider details", () => {
  assert.match(googleCallbackError("access_denied"), /cancelled/);
  assert.match(googleCallbackError("private-provider-detail"), /couldn't finish/);
  assert.doesNotMatch(googleCallbackError("private-provider-detail"), /private-provider-detail/);
});
