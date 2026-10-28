import axios from "axios";

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) return fallback;
  const detail: unknown = error.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = String(detail.message).trim();
    if (message) return message;
  }
  if (!error.response) return "Matchgoer is unavailable right now. Check your connection and try again.";
  return fallback;
}

// Only an explicit successful guest-session response proves an empty guest.
// Missing fields and authenticated/session-error states must still load or fail.
export function emptyGuestHistory(session: unknown, authenticated: boolean, sessionIssue: unknown): boolean {
  if (authenticated || sessionIssue || !session || typeof session !== "object") return false;
  const value = session as { anonymous?: unknown; anonymous_activity?: unknown };
  return value.anonymous === true && value.anonymous_activity === false;
}

export function historyLoadError(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error) && error.response?.status === 401
    && error.response.data?.detail?.code === "NO_ACTIVE_IDENTITY") {
    return "We couldn't access your saved history. Please try again.";
  }
  return apiErrorMessage(error, fallback);
}
