import Link from "next/link";

import AccountShell from "@/app/components/AccountShell";
import { safeReturnTo } from "@/lib/auth-flow";

export default async function AccountConflictPage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) {
  const { returnTo } = await searchParams;
  const destination = safeReturnTo(returnTo);
  return <AccountShell kicker="Signed in" title="You're signed in" intro="There's also Matchgoer activity on this device that isn't attached to this account yet.">
    <p className="mt-5 leading-7">We’ll add a safe way to bring it across soon. Nothing on this device or in your account has been changed.</p>
    <Link href={destination} className="tt-action mt-6 inline-flex items-center justify-center px-5">Continue to my account</Link>
  </AccountShell>;
}
