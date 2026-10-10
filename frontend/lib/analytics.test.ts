import assert from "node:assert/strict";
import test from "node:test";
import { acceptAnalytics, allowedParameters, configureAnalytics, consentKey, measurementId, readConsent, registrationCompleted, registrationStarted, resultBucket, safePage, safeReferrer, setAnalyticsEnabled, trackEvent, trackPage, withdrawAnalytics } from "./analytics.ts";

test("only allowlisted page families, never queries, identities or callback routes", () => {
  assert.equal(safePage("/fixture/42?handoff=secret#token"), "/fixture");
  assert.equal(safePage("/venue/9"), "/venue");
  assert.equal(safePage("/my-football?tab=visited"), "/my-football");
  for (const path of ["/auth/callback", "/signup", "/signin", "/account/onboarding", "/users/name", "/fixture/name"]) assert.equal(safePage(path), null);
});
test("strict event/parameter/value allowlists discard identifying content", () => {
  assert.equal(allowedParameters("unknown", {}), null);
  assert.deepEqual(allowedParameters("fixture_saved", { surface: "discover", fixture_id: 42, email: "private", latitude: 1, action: "anything" }), { surface: "discover" });
  assert.deepEqual(allowedParameters("location_search", { search_method: "raw city", result_count_bucket: "1-10", query: "Stockholm" }), { result_count_bucket: "1-10" });
});
test("result buckets are bounded", () => {
  assert.deepEqual([0, 1, 10, 11, 50, 51].map(resultBucket), ["0", "1-10", "1-10", "11-50", "11-50", "51+"]);
});
test("referrers preserve only external origins, never auth/query/fragment details", () => {
  assert.equal(safeReferrer("https://example.com/private?email=secret#token", "https://beta.matchgoer.com"), "https://example.com/");
  assert.equal(safeReferrer("https://beta.matchgoer.com/auth/callback?code=secret", "https://beta.matchgoer.com"), "");
  assert.equal(safeReferrer("javascript:secret", "https://beta.matchgoer.com"), "");
});
test("consent, navigation deduplication, registration and withdrawal gating", () => {
  const storage = new Map<string, string>();
  const fakeStorage = { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value), removeItem: (key: string) => storage.delete(key) };
  const fakeWindow = { location: { pathname: "/", origin: "https://beta.matchgoer.com" }, dispatchEvent: () => true, dataLayer: [] as unknown[], [`ga-disable-${measurementId}`]: true };
  Object.defineProperty(globalThis, "window", { configurable: true, value: fakeWindow });
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: fakeStorage });
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: fakeStorage });
  assert.equal(readConsent(), null);
  assert.equal(trackEvent("fixture_saved", { surface: "discover" }), false);
  configureAnalytics(); assert.equal(fakeWindow.dataLayer.length, 0);
  storage.set(consentKey, "rejected"); assert.equal(readConsent(), "rejected");
  storage.set(consentKey, "accepted"); setAnalyticsEnabled(true); configureAnalytics(); trackPage("/"); trackPage("/");
  const commands = () => fakeWindow.dataLayer.map(command => Array.from(command as ArrayLike<unknown>));
  assert.equal(commands().filter(command => command[1] === "page_view").length, 1);
  fakeWindow.location.pathname = "/fixture/42";
  trackPage("/fixture/42");
  assert.equal(trackEvent("fixture_view", { surface: "fixture" }, "loaded"), true);
  assert.equal(trackEvent("fixture_view", { surface: "fixture" }, "loaded"), false);
  fakeWindow.location.pathname = "/fixture/43"; trackPage("/fixture/43"); assert.equal(trackEvent("fixture_view", { surface: "fixture" }, "loaded"), true);
  fakeWindow.location.pathname = "/"; trackPage("/"); fakeWindow.location.pathname = "/fixture/42"; trackPage("/fixture/42"); assert.equal(trackEvent("fixture_view", { surface: "fixture" }, "loaded"), true);
  const beforeSignup = commands().filter(command => command[1] === "sign_up").length;
  fakeWindow.location.pathname = "/";
  registrationCompleted(); trackPage("/"); assert.equal(commands().filter(command => command[1] === "sign_up").length, beforeSignup);
  registrationStarted(); registrationCompleted(); trackPage("/"); trackPage("/");
  assert.equal(commands().filter(command => command[1] === "sign_up").length, beforeSignup + 1);
  fakeWindow.location.pathname = "/auth/callback";
  assert.equal(trackEvent("fixture_saved", { surface: "fixture" }), false);
  setAnalyticsEnabled(false);
  assert.equal(trackEvent("going_selected", { surface: "matchdays" }), false);
  assert.equal(fakeWindow[`ga-disable-${measurementId}`], true);
  assert.equal(JSON.stringify(commands()).includes("handoff"), false);
  assert.equal(JSON.stringify(commands()).includes("fixture/42"), false);
  const config = commands().find(command => command[0] === "config")![2] as Record<string, unknown>;
  assert.equal(config.send_page_view, false); assert.equal(config.allow_google_signals, false);
  Object.defineProperty(globalThis, "document", { configurable: true, value: { cookie: "" } });
  fakeStorage.setItem = () => { throw new Error("Storage unavailable"); };
  fakeWindow.location.pathname = "/";
  withdrawAnalytics(); setAnalyticsEnabled(true);
  assert.equal(trackEvent("fixture_saved", { surface: "discover" }), false, "Withdrawal remains effective even if saving preference fails");
  assert.equal(fakeWindow[`ga-disable-${measurementId}`], true);
  acceptAnalytics(); setAnalyticsEnabled(false);
  delete (globalThis as Record<string, unknown>).document;
  delete (globalThis as Record<string, unknown>).window;
  delete (globalThis as Record<string, unknown>).localStorage;
  delete (globalThis as Record<string, unknown>).sessionStorage;
});
