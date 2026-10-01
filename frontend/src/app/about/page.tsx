import type { Metadata } from "next";
import { auth } from "@clerk/nextjs/server";
import Landing from "@/components/landing";

export const metadata: Metadata = {
  title: "حال‌خوب — دانلود و آرشیو شخصی ویدیوها",
  description: "ویدیوهای یوتیوب و اینستاگرام را دانلود کن، دسته‌های خودت را بساز و در آرشیو شخصی‌ات تماشا کن یا به صدایشان گوش بده.",
};

export default async function AboutPage() {
  const { userId } = await auth();
  return <Landing signedIn={Boolean(userId)} />;
}
