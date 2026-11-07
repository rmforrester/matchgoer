"use client";
import { useEffect, useState, type ReactNode } from "react";
import { mapPlatform, placeUrlFromVerifiedUrl } from "../../lib/map-destination";

export default function DestinationLink({ url, className, id, destinationName, children = "View on map →" }: { url: string | null; className?: string; id?: string; destinationName?: string; children?: ReactNode }) {
  const [platform, setPlatform] = useState<"apple" | "google">("google");
  useEffect(() => { const frame = requestAnimationFrame(() => setPlatform(mapPlatform())); return () => cancelAnimationFrame(frame); }, []);
  const href = placeUrlFromVerifiedUrl(url, platform, destinationName);
  return href ? <a id={id} href={href} target="_blank" rel="noopener noreferrer" className={className}>{children}</a> : null;
}
