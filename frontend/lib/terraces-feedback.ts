export type PhotoFeedback = { kind: "success" | "error"; text: string };
export function uploadFeedback(sent: number, total: number, failure: string, published = 0, uncertain = false): PhotoFeedback {
  const shared = published ? `${published} ${published === 1 ? "photo" : "photos"} shared.` : "";
  const pending = sent - published;
  if (sent === total) return { kind: "success", text: published === sent ? sent === 1 ? "Photo shared." : "Photos shared." : published ? `${shared} ${pending} ${pending === 1 ? "photo" : "photos"} sent. Pending review.` : sent === 1 ? "Photo sent. Pending review." : "Photos sent. Pending review." };
  if (sent === 0) return { kind: "error", text: failure };
  const remaining = total - sent;
  const remainingText = uncertain ? remaining === 1 ? "We couldn't confirm one" : `We couldn't confirm ${remaining}` : remaining === 1 ? "One didn't go through" : `${remaining} still need to go through`;
  const confirmed = published ? `${shared}${pending ? ` ${pending} ${pending === 1 ? "photo" : "photos"} sent.` : ""}` : `${sent} ${sent === 1 ? "photo" : "photos"} sent.`;
  return { kind: "error", text: `${confirmed} ${remainingText} — try again.` };
}
export function uncertainPhotoResponse(error: unknown): boolean {
  const status = (error as { response?: { status?: number } })?.response?.status;
  return !status || status >= 500;
}
export function refreshFailure(confirmed?: PhotoFeedback): PhotoFeedback {
  return { kind: confirmed?.kind ?? "error", text: confirmed ? `${confirmed.text} Can't load your photos right now.` : "Can't connect right now. Try again in a moment." };
}
