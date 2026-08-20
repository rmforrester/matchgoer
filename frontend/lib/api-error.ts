import axios from "axios";

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) return fallback;
  const detail: unknown = error.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = String(detail.message).trim();
    if (message) return message;
  }
  if (!error.response) return "Terrace Talk is unavailable right now. Check your connection and try again.";
  return fallback;
}
