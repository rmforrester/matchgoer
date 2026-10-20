"use client";

import { useEffect, useId, useState } from "react";
import api from "@/lib/api";
import type { PhotoAttendance } from "@/lib/terraces";
import { useAuth } from "./AuthProvider";
import TerracePhotoSubmission from "./TerracePhotoSubmission";

export default function FixturePhotoSharing({ attendance }: { attendance: PhotoAttendance }) {
  const { authenticated, accountKey } = useAuth();
  return authenticated ? <OwnedFixturePhotos key={`${accountKey}:${attendance.visit_id}`} attendance={attendance} /> : null;
}

function OwnedFixturePhotos({ attendance }: { attendance: PhotoAttendance }) {
  const [allowed, setAllowed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const panelId = useId();

  useEffect(() => {
    const controller = new AbortController();
    // Ownership and permission come from the existing server contract, never
    // from a public user ID or the fact that someone can read their own photos.
    void api.get<{ can_submit?: boolean }>(`/terraces/visits/${attendance.visit_id}/photos`, { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setAllowed(data.can_submit === true); })
      .catch(() => { if (!controller.signal.aborted) setAllowed(false); });
    return () => controller.abort();
  }, [attendance.visit_id]);

  if (!allowed) return null;
  return <>
    <button type="button" className="mg-tertiary-action inline-flex min-h-11 items-center uppercase" aria-expanded={expanded} aria-controls={panelId} onClick={() => setExpanded(value => !value)}>{expanded ? "Hide photos" : "Add photos →"}</button>
    {expanded && <div id={panelId} className="w-full min-w-0 basis-full"><TerracePhotoSubmission attendance={attendance} /></div>}
  </>;
}
