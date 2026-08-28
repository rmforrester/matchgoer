import SigninForm from "./SigninForm";

export default async function SigninPage({ searchParams }: { searchParams: Promise<{ returnTo?: string; handoff?: string }> }) {
  const { returnTo, handoff } = await searchParams;
  return <SigninForm returnTo={returnTo} handoffToken={handoff} />;
}
