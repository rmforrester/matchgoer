"use client";
import Link from "next/link";
import styles from "./MapFixtureActions.module.css";

export type MapSaveActions = {
  interestedFixtureIds: number[];
  updatingFixtureIds: number[];
  onToggleInterested: (fixtureId: number) => void;
};
export default function MapFixtureActions({ fixtureId, interestedFixtureIds, updatingFixtureIds, onToggleInterested }: MapSaveActions & { fixtureId: number }) {
  const saved = interestedFixtureIds.includes(fixtureId);
  const busy = updatingFixtureIds.includes(fixtureId);
  return <div className={styles.container}><div className={styles.actions}>
    <Link href={`/fixture/${fixtureId}`} className={styles.view}>VIEW MATCH</Link>
    <button type="button" className={styles.save} disabled={busy} aria-busy={busy} aria-pressed={saved} onClick={() => onToggleInterested(fixtureId)}><span>{saved ? "REMOVE FROM MY MATCHDAYS" : "ADD TO MY MATCHDAYS"}</span></button>
  </div></div>;
}
