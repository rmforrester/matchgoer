"use client";

import { useState } from "react";

type Props = {
  src?: string | null;
  className?: string;
};

export default function TeamBadge({ src, className = "" }: Props) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);

  if (!src || failedSrc === src) return null;

  return (
    <span className={`inline-flex shrink-0 items-center justify-center ${className}`} aria-hidden="true">
      {/* A decorative image beside an already visible team name; failure collapses the slot. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt=""
        className="block h-full w-full object-contain"
        loading="eager"
        decoding="async"
        onError={() => setFailedSrc(src)}
      />
    </span>
  );
}
