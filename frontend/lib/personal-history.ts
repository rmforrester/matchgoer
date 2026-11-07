export const PERSONAL_HISTORY_CHANGED = "matchgoer:personal-history-changed";

export function changesPersonalHistory(method: string | undefined, url: string | undefined): boolean {
  return /^(post|patch|put|delete)$/i.test(method ?? "") &&
    /^\/(?:venues\/\d+\/(?:visits(?:\/\d+)?|collection)|fixtures\/\d+\/(?:attendance|interested|going))(?:\?|$)/.test(url ?? "");
}

export function notifyPersonalHistoryChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(PERSONAL_HISTORY_CHANGED));
}
