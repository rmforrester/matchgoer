import Link from "next/link";

import AccountShell from "@/app/components/AccountShell";
import { safeReturnTo } from "@/lib/auth-flow";

export default async function AccountReadyPage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) {
  const { returnTo } = await searchParams;
  const destination = safeReturnTo(returnTo);
  return <AccountShell kicker="Signed in" title="Your matchday activity is saved" intro="Anything you did before signing in has been added to your account.">
    <Link href={destination} className="tt-action mt-6 inline-flex items-center justify-center px-5">Continue →</Link>
  </AccountShell>;
}
