import { redirect } from "next/navigation";

type Props = {
  searchParams: Promise<{
    review?: string | string[];
  }>;
};

export default async function MyStadiumsRedirect({ searchParams }: Props) {
  const { review } = await searchParams;
  const destination = new URLSearchParams({ tab: "visited" });

  if (typeof review === "string") {
    destination.set("review", review);
  }

  redirect(`/my-football?${destination.toString()}`);
}
