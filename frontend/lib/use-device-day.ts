"use client";

import { useSyncExternalStore } from "react";
import { localCalendarDateValue } from "./fixtureDiscovery";

const listeners = new Set<() => void>();
let timer: ReturnType<typeof setTimeout> | undefined;
function snapshot() {
  const now = new Date();
  return `${localCalendarDateValue(now)}:${now.getTimezoneOffset()}:${Intl.DateTimeFormat().resolvedOptions().timeZone}`;
}
function tick() {
  for (const notify of listeners) notify();
  clearTimeout(timer);
  const now = new Date();
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  // One shared timer; also notice device clock/timezone changes while foregrounded.
  timer = setTimeout(tick, Math.min(60_000, Math.max(20, midnight.getTime() - now.getTime() + 20)));
}
function subscribe(notify: () => void) {
  listeners.add(notify);
  if (listeners.size === 1) {
    window.addEventListener("focus", tick);
    document.addEventListener("visibilitychange", tick);
    tick();
  }
  return () => {
    listeners.delete(notify);
    if (!listeners.size) {
      clearTimeout(timer);
      window.removeEventListener("focus", tick);
      document.removeEventListener("visibilitychange", tick);
    }
  };
}
export function useDeviceDay() {
  useSyncExternalStore(subscribe, snapshot, () => "");
  return new Date();
}
