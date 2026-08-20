export const WHOS_GOING_ENABLE = "whos-going-enable" as const;
export const PENDING_ACTION_MAX_AGE_MS = 30 * 60 * 1000;

const ACTION_PARAM = "pendingAction";
const FIXTURE_PARAM = "pendingFixtureId";
const ISSUED_AT_PARAM = "pendingIssuedAt";

export type PendingWhosGoingAction = {
  action: typeof WHOS_GOING_ENABLE;
  fixtureId: number;
  issuedAt: number;
};

function validFixtureId(value: string | null) {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const fixtureId = Number(value);
  return Number.isSafeInteger(fixtureId) ? fixtureId : null;
}

export function pendingWhosGoingReturnTo(fixtureId: number, now = Date.now()) {
  if (!Number.isSafeInteger(fixtureId) || fixtureId <= 0) throw new Error("Invalid fixture id");
  const params = new URLSearchParams({
    [ACTION_PARAM]: WHOS_GOING_ENABLE,
    [FIXTURE_PARAM]: String(fixtureId),
    [ISSUED_AT_PARAM]: String(now),
  });
  return `/fixture/${fixtureId}?${params.toString()}`;
}

export function parsePendingWhosGoingAction(
  params: URLSearchParams,
  expectedFixtureId: number,
  now = Date.now(),
): PendingWhosGoingAction | null {
  if (params.get(ACTION_PARAM) !== WHOS_GOING_ENABLE) return null;
  const fixtureId = validFixtureId(params.get(FIXTURE_PARAM));
  const issuedAtValue = params.get(ISSUED_AT_PARAM);
  if (!issuedAtValue || !/^\d+$/.test(issuedAtValue)) return null;
  const issuedAt = Number(issuedAtValue);
  if (!Number.isSafeInteger(issuedAt) || issuedAt > now + 60_000 || now - issuedAt > PENDING_ACTION_MAX_AGE_MS) return null;
  if (fixtureId !== expectedFixtureId) return null;
  return { action: WHOS_GOING_ENABLE, fixtureId, issuedAt };
}

export function hasPendingAuthAction(params: URLSearchParams) {
  return params.has(ACTION_PARAM) || params.has(FIXTURE_PARAM) || params.has(ISSUED_AT_PARAM);
}

