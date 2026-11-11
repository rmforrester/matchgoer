"use client";

import { useEffect, useState } from "react";
import api from "../../lib/api";
import MapDirections from "./MapDirections";

export default function FixtureDirections({ venueId }: { venueId: number | null }) {
  const [destination, setDestination] = useState<{ venueId: number; latitude: number; longitude: number; name: string } | null>(null);
  useEffect(() => {
    if (!venueId || !Number.isSafeInteger(venueId) || venueId <= 0) return;
    const controller = new AbortController();
    api.get(`/venue/${venueId}`, { signal: controller.signal }).then(({ data }) => {
      const { latitude, longitude } = data ?? {};
      if (!controller.signal.aborted && Number.isFinite(latitude) && Number.isFinite(longitude) && Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180) {
        setDestination({ venueId, latitude, longitude, name: data.name ?? "" });
      }
    }).catch(() => { /* No valid canonical destination: omit directions. */ });
    return () => controller.abort();
  }, [venueId]);
  if (!destination || destination.venueId !== venueId) return null;
  return <MapDirections latitude={destination.latitude} longitude={destination.longitude} name={destination.name} />;
}
