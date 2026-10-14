"use client";
import { useEffect, useState } from "react";

export default function TerracePhotoPreview({ file }: { file: File }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const preview = URL.createObjectURL(file);
    const timer = window.setTimeout(() => { setUrl(preview); setFailed(false); }, 0);
    return () => { window.clearTimeout(timer); URL.revokeObjectURL(preview); };
  }, [file]);
  return <div className="flex min-h-24 min-w-0 items-center justify-center bg-[var(--tt-paper)]">
    {url && !failed ? <>
      {/* Browser-local originals; never sent to a public image optimiser. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={url} alt="Selected photograph preview" onError={() => setFailed(true)} className="max-h-32 w-full object-contain" />
    </> : <p className="p-2 text-xs font-normal text-[var(--tt-muted)]">{failed ? "Can't preview this photo here. You can still share it." : "Preparing preview…"}</p>}
  </div>;
}
