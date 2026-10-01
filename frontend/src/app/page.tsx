import { auth } from "@clerk/nextjs/server";
import Archive from "@/components/archive";
import Landing from "@/components/landing";

export default async function Page() {
  const { userId } = await auth();
  return userId ? <Archive /> : <Landing />;
}
