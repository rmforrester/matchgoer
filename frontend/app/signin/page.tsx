import SigninForm from "./SigninForm";

export default async function SigninPage({ searchParams }: { searchParams: Promise<{ returnTo?: string; handoff?: string; convert?: string }> }) {
  const { returnTo, handoff, convert } = await searchParams;
  return <SigninForm returnTo={returnTo} handoffToken={handoff} convertAnonymous={convert === "1"} />;
}
