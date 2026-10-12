import AuthEmailForm from "@/app/components/AuthEmailForm";
export default async function ForgotPasswordPage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) {
  const { returnTo } = await searchParams;
  return <AuthEmailForm kind="recovery" returnTo={returnTo} />;
}
