// Deliberately no account, fixture, location or free-text identifiers.
export const measurementId = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID || "G-JNMM0SKS3F";
export const consentKey = "matchgoer.analytics-consent.v1";
export type Consent = "accepted" | "rejected";
const schema = {
  location_search: { search_method: ["location", "map"], result_count_bucket: ["0", "1-10", "11-50", "51+"] },
  fixture_view: { surface: ["fixture"] },
  decide_engagement: { section: ["decide"], action: ["exposure"] },
  know_engagement: { section: ["know"], action: ["exposure"] },
  ticket_click: { surface: ["fixture"], ticket_type: ["online", "information", "unspecified"] },
  fixture_saved: { surface: ["discover", "fixture"] },
  going_selected: { surface: ["matchdays"] },
  going_removed: { surface: ["matchdays"] },
  sign_up: { surface: ["account"] },
  attendance_recorded: { surface: ["matchdays"] },
} as const;
export type AnalyticsEvent = keyof typeof schema;
type AnalyticsWindow = Window & { dataLayer?: unknown[]; gtag?: (...args: unknown[]) => void } & Partial<Record<`ga-disable-${string}`, boolean>>;
let enabled = false;
let withdrawn = false;
let configured = false;
let currentNavigation = "";
let lastPage = "";
const recorded = new Set<string>();
let pendingRegistration = false;
let entryReferrer = "";

export function safeReferrer(value: string, ownOrigin: string) {
  try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) && url.origin !== ownOrigin ? `${url.origin}/` : ""; }
  catch { return ""; }
}

export function safePage(path: string): string | null {
  const clean = path.split(/[?#]/)[0];
  if (clean === "/") return "/";
  if (/^\/fixture\/\d+\/?$/.test(clean)) return "/fixture";
  if (/^\/venue\/\d+\/?$/.test(clean)) return "/venue";
  return ["/my-football", "/my-stadiums", "/privacy"].includes(clean) ? clean : null;
}

export function allowedParameters(event: string, parameters: Record<string, unknown>) {
  if (!Object.hasOwn(schema, event)) return null;
  const rules = schema[event as AnalyticsEvent] as Record<string, readonly string[]>;
  return Object.fromEntries(Object.entries(parameters).filter(([key, value]) => typeof value === "string" && rules[key]?.includes(value)));
}

export function readConsent(): Consent | null {
  try { const value = localStorage.getItem(consentKey); return value === "accepted" || value === "rejected" ? value : null; }
  catch { return null; }
}

export function setAnalyticsEnabled(value: boolean) {
  enabled = value && !withdrawn;
  if (typeof window !== "undefined") (window as unknown as AnalyticsWindow)[`ga-disable-${measurementId}`] = !enabled;
}
export function acceptAnalytics() { withdrawn = false; }

export function trackEvent(event: AnalyticsEvent, parameters: Record<string, unknown> = {}, once?: string) {
  if (!enabled || typeof window === "undefined" || !configured || !safePage(window.location.pathname)) return false;
  const safe = allowedParameters(event, parameters);
  if (!safe) return false;
  if (currentNavigation !== window.location.pathname) { currentNavigation = window.location.pathname; recorded.clear(); }
  (window as unknown as AnalyticsWindow).gtag?.("set", { page_location: `${window.location.origin}${safePage(window.location.pathname)}`, page_title: "Matchgoer", page_referrer: entryReferrer });
  const key = once ? `${currentNavigation}:${event}:${once}` : null;
  if (key && recorded.has(key)) return false;
  if (key) recorded.add(key);
  (window as unknown as AnalyticsWindow).gtag?.("event", event, safe);
  return true;
}

export function configureAnalytics() {
  if (!enabled || configured || typeof window === "undefined") return;
  const target = window as unknown as AnalyticsWindow;
  entryReferrer = safeReferrer(typeof document === "undefined" ? "" : document.referrer, window.location.origin);
  target.dataLayer ??= [];
  // Google requires arguments objects in its command queue.
  // eslint-disable-next-line prefer-rest-params -- Google's queue expects an Arguments object.
  target.gtag = function () { target.dataLayer!.push(arguments); };
  target.gtag("consent", "default", { analytics_storage: "granted", ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied" });
  target.gtag("js", new Date());
  target.gtag("config", measurementId, {
    send_page_view: false, allow_google_signals: false, allow_ad_personalization_signals: false,
    page_location: `${window.location.origin}${safePage(window.location.pathname) ?? "/"}`,
    page_title: "Matchgoer", page_referrer: entryReferrer, cookie_expires: 60 * 60 * 24 * 60,
  });
  configured = true;
}

export function trackPage(path: string) {
  if (typeof window === "undefined") return;
  if (currentNavigation !== path) { currentNavigation = path; recorded.clear(); }
  const page = safePage(path);
  if (!enabled || !configured || !page) { lastPage = ""; return; }
  const target = window as unknown as AnalyticsWindow;
  target.gtag?.("set", { page_location: `${window.location.origin}${page}`, page_title: "Matchgoer", page_referrer: entryReferrer });
  if (lastPage !== path) {
    lastPage = path;
    target.gtag?.("event", "page_view", { page_location: `${window.location.origin}${page}`, page_title: "Matchgoer", page_referrer: entryReferrer });
  }
  if (pendingRegistration) { pendingRegistration = false; trackEvent("sign_up", { surface: "account" }); }
  window.dispatchEvent(new Event("matchgoer-analytics-ready"));
}

// First non-idempotent claim only; dispatch on a safe destination, never the callback.
export function registrationStarted() {
  if (readConsent() === "accepted") try { sessionStorage.setItem("matchgoer.analytics-registration", "pending"); } catch { /* No telemetry. */ }
}
export function registrationCompleted() {
  try {
    if (sessionStorage.getItem("matchgoer.analytics-registration") === "pending" && readConsent() === "accepted") pendingRegistration = true;
    sessionStorage.removeItem("matchgoer.analytics-registration");
  } catch { /* No telemetry. */ }
}
export function resultBucket(count: number) { return count === 0 ? "0" : count <= 10 ? "1-10" : count <= 50 ? "11-50" : "51+"; }

export function withdrawAnalytics() {
  withdrawn = true;
  setAnalyticsEnabled(false);
  pendingRegistration = false;
  if (typeof window === "undefined") return;
  (window as unknown as AnalyticsWindow).dataLayer = [];
  let remembered = false;
  try { localStorage.setItem(consentKey, "rejected"); remembered = true; } catch { /* Keep the loaded document disabled if storage is unavailable. */ }
  // Remove GA cookies at host and parent-domain scopes. Reload removes the loaded tag.
  for (const entry of document.cookie.split(";")) {
    const name = entry.trim().split("=")[0];
    if (!/^_ga(?:_|$)/.test(name)) continue;
    const labels = window.location.hostname.split(".");
    document.cookie = `${name}=; Max-Age=0; path=/`;
    for (let index = 0; index < labels.length - 1; index++) document.cookie = `${name}=; Max-Age=0; path=/; domain=.${labels.slice(index).join(".")}`;
  }
  if (remembered) window.location.reload();
}
