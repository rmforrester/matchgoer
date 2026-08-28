import { parsePendingWhosGoingAction, type PendingWhosGoingAction } from "./pending-auth-action.ts";

const HANDOFF_KEY = "matchgoer.account-conversion.v1";
const PENDING_ACTION_KEY = "matchgoer.pending-auth-action.v1";

export type BrowserStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

type StoredHandoff = { token: string; expiresAt: string; returnTo: string };

function storage(): BrowserStorage | null {
  return typeof window === "undefined" ? null : window.localStorage;
}

export function saveConversionHandoff(value: StoredHandoff, target = storage()) {
  target?.setItem(HANDOFF_KEY, JSON.stringify(value));
}

export function loadConversionHandoff(now = Date.now(), target = storage()): StoredHandoff | null {
  if (!target) return null;
  try {
    const value = JSON.parse(target.getItem(HANDOFF_KEY) ?? "null") as Partial<StoredHandoff> | null;
    if (!value || typeof value.token !== "string" || value.token.length < 32 || typeof value.expiresAt !== "string" || typeof value.returnTo !== "string") throw new Error("invalid handoff");
    if (!Number.isFinite(Date.parse(value.expiresAt)) || Date.parse(value.expiresAt) <= now) throw new Error("expired handoff");
    return value as StoredHandoff;
  } catch {
    target.removeItem(HANDOFF_KEY);
    return null;
  }
}

export function clearConversionHandoff(target = storage()) {
  target?.removeItem(HANDOFF_KEY);
}

export async function clearConversionHandoffAfter<T>(operation: Promise<T>, target = storage()) {
  const result = await operation;
  clearConversionHandoff(target);
  return result;
}

export function savePendingWhosGoingFromReturnTo(returnTo: string, now = Date.now(), target = storage()) {
  if (!target) return null;
  const url = new URL(returnTo, "https://matchgoer.invalid");
  const fixtureId = Number(url.pathname.match(/^\/fixture\/(\d+)$/)?.[1]);
  const pending = parsePendingWhosGoingAction(url.searchParams, fixtureId, now);
  if (!pending) return null;
  target.setItem(PENDING_ACTION_KEY, JSON.stringify(pending));
  return pending;
}

export function loadPendingWhosGoing(expectedFixtureId: number, now = Date.now(), target = storage()): PendingWhosGoingAction | null {
  if (!target) return null;
  try {
    const value = JSON.parse(target.getItem(PENDING_ACTION_KEY) ?? "null") as Partial<PendingWhosGoingAction> | null;
    if (!value) return null;
    const params = new URLSearchParams({
      pendingAction: String(value.action ?? ""),
      pendingFixtureId: String(value.fixtureId ?? ""),
      pendingIssuedAt: String(value.issuedAt ?? ""),
    });
    const pending = parsePendingWhosGoingAction(params, expectedFixtureId, now);
    if (!pending) throw new Error("invalid pending action");
    return pending;
  } catch {
    target.removeItem(PENDING_ACTION_KEY);
    return null;
  }
}

export function clearPendingWhosGoing(target = storage()) {
  target?.removeItem(PENDING_ACTION_KEY);
}

type SocialConfirmation = { interested: boolean; open_to_meet: boolean };

export async function applyPendingWhosGoing(
  pending: PendingWhosGoingAction,
  put: (fixtureId: number) => Promise<SocialConfirmation>,
  read: () => Promise<SocialConfirmation>,
) {
  const updated = await put(pending.fixtureId);
  if (!updated.interested || !updated.open_to_meet) throw new Error("Pending action was not confirmed");
  const authoritative = await read();
  if (!authoritative.interested || !authoritative.open_to_meet) throw new Error("Authoritative social state did not confirm the pending action");
  return authoritative;
}
