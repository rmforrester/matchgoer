import Recovery from "./Recovery";
export default async function RecoveryPage({ searchParams }: { searchParams: Promise<{ returnTo?: string; error?: string }> }) {
  const { returnTo, error } = await searchParams;
  return <Recovery returnTo={returnTo} providerError={Boolean(error)} />;
}
