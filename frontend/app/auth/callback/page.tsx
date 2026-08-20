import AuthCallback from "./AuthCallback";

export default async function AuthCallbackPage({ searchParams }: { searchParams: Promise<{ code?: string; returnTo?: string; error?: string }> }) {
  const params = await searchParams;
  return <AuthCallback code={params.code} returnTo={params.returnTo} providerError={params.error} />;
}
