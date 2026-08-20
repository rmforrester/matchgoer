import SigninForm from "./SigninForm";

export default async function SigninPage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) {
  const { returnTo } = await searchParams;
  return <SigninForm returnTo={returnTo} />;
}
