import AuthEmailForm from "@/app/components/AuthEmailForm";
export default async function ConfirmationPage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) {
  const { returnTo } = await searchParams;
  return <AuthEmailForm kind="signup" returnTo={returnTo} />;
}
