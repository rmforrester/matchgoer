import { redirect } from "next/navigation";

export default function InterestedRedirect() {
  redirect("/my-football?tab=interested");
}
