import Link from "next/link";

import AccountShell from "@/app/components/AccountShell";
import { safeReturnTo } from "@/lib/auth-flow";

export default async function AccountConflictPage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) {
  const { returnTo } = await searchParams;
  const destination = safeReturnTo(returnTo);
  return <AccountShell kicker="Signed in" title="Account conversion paused" intro="We couldn't safely verify the saved Matchgoer activity on this device.">
    <p className="mt-5 leading-7">Nothing has been moved to a different supporter. Return to the original browser to retry, or continue to your account.</p>
    <Link href={destination} className="tt-action mt-6 inline-flex items-center justify-center px-5">Continue to my account</Link>
  </AccountShell>;
}
