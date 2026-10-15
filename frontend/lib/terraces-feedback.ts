export type PhotoFeedback = { kind: "success" | "error"; text: string };
export function uploadFeedback(sent: number, total: number, failure: string, alreadyReviewed = false, uncertain = false): PhotoFeedback {
  if (sent === total) return { kind: "success", text: alreadyReviewed ? "Your photos are saved." : sent === 1 ? "Photo sent. Pending review." : "Photos sent. Pending review." };
  if (sent === 0) return { kind: "error", text: failure };
  const remaining = total - sent;
  const remainingText = uncertain ? remaining === 1 ? "We couldn't confirm one" : `We couldn't confirm ${remaining}` : remaining === 1 ? "One didn't go through" : `${remaining} still need to go through`;
  return { kind: "error", text: `${sent} ${sent === 1 ? "photo" : "photos"} sent. ${remainingText} — try again.` };
}
export function uncertainPhotoResponse(error: unknown): boolean {
  const status = (error as { response?: { status?: number } })?.response?.status;
  return !status || status >= 500;
}
export function refreshFailure(confirmed?: PhotoFeedback): PhotoFeedback {
  return { kind: confirmed?.kind ?? "error", text: confirmed ? `${confirmed.text} Can't load your photos right now.` : "Can't connect right now. Try again in a moment." };
}
