"use client";

import { formatFixtureDate, formatKickoffTime } from "../../lib/fixture-format";
import { useDeviceDay } from "../../lib/use-device-day";

export default function FixtureDateTime({ value, dateOnly = false, long = false }: { value: string; dateOnly?: boolean; long?: boolean }) {
  const now = useDeviceDay();
  if (!Number.isFinite(new Date(value).getTime())) return <span>Kick-off to be confirmed</span>;
  const date = formatFixtureDate(value, now, long ? { weekday: "long", month: "long", year: "numeric" } : {});
  return <time dateTime={value}><span className="whitespace-nowrap">{date}</span>{!dateOnly && <> · <span className="whitespace-nowrap">{formatKickoffTime(value)}</span></>}</time>;
}
