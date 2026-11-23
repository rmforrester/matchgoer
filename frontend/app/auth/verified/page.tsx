import type { Metadata } from "next";
import VerificationReturn from "./VerificationReturn";

export const metadata: Metadata = {
  title: "Confirm your email — Matchgoer",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function VerificationPage() {
  return <VerificationReturn />;
}
