"use client";

import { useEffect, useMemo } from "react";
import Link from "next/link";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

import type { MyGround } from "../types/grounds";
import { createGroundMarkerIcon } from "./groundMarkerIcon";

type Props = { grounds: MyGround[] };

const displayDate = (value: string | null) => value
  ? new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
  : null;

function FitVisitedBounds({ grounds }: Props) {
  const map = useMap();
  useEffect(() => {
    const points = grounds.flatMap((ground) => ground.latitude !== null && ground.longitude !== null
      ? [[ground.latitude, ground.longitude] as [number, number]]
      : []);
    if (points.length === 1) map.setView(points[0], 7);
    if (points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [28, 28], maxZoom: 8 });
  }, [grounds, map]);
  return null;
}

export default function PersonalGroundMap({ grounds }: Props) {
  const plottable = grounds.filter((ground) => ground.latitude !== null && ground.longitude !== null);
  const icon = useMemo(() => createGroundMarkerIcon(true), []);

  if (plottable.length === 0) return <div className="flex h-56 items-center justify-center border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] p-6 text-center sm:h-72"><p className="max-w-md font-semibold text-[var(--tt-muted)]">Your grounds do not have coordinates yet, so they cannot be shown on the map.</p></div>;

  return (
    <div className="h-56 overflow-hidden border-2 border-[var(--tt-ink)] bg-[var(--tt-paper)] sm:h-72">
      <MapContainer center={[20, 0]} zoom={2} className="h-full w-full" scrollWheelZoom={false}>
        <FitVisitedBounds grounds={plottable}/>
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
        {plottable.map((ground) => <Marker key={ground.venue_id} position={[ground.latitude as number, ground.longitude as number]} icon={icon} title={`${ground.venue_name}, visited ground`} alt={`${ground.venue_name}, visited ground`}><Popup><strong>{ground.venue_name}</strong>{(ground.venue_city || ground.venue_country) && <><br/>{[ground.venue_city, ground.venue_country].filter(Boolean).join(" · ")}</>}<br/><br/><strong>{ground.visit_count} {ground.visit_count === 1 ? "visit" : "visits"}</strong>{ground.first_visit_date && <><br/>First known: {displayDate(ground.first_visit_date)}</>}{ground.latest_visit_date && <><br/>Latest: {displayDate(ground.latest_visit_date)}</>}<div><Link href={`/venue/${ground.venue_id}`} className="mt-3 inline-flex min-h-11 items-center font-extrabold uppercase tracking-[0.08em] text-[var(--tt-blue)] underline decoration-2 underline-offset-4">View ground →</Link></div></Popup></Marker>)}
      </MapContainer>
    </div>
  );
}
