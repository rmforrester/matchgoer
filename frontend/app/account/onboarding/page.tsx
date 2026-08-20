import ProfileOnboarding from "./ProfileOnboarding";

export default async function ProfileOnboardingPage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) {
  const { returnTo } = await searchParams;
  return <ProfileOnboarding returnTo={returnTo} />;
}
