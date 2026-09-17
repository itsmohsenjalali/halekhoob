import { SignUp } from "@clerk/nextjs";
import BrandMark from "@/components/brand-mark";
export default function Page() {
  return (
    <main className="auth-page">
      <a className="brand" href="/">
        <BrandMark size={76} />
        حال‌خوب
      </a>
      <h1>آرشیو شخصی‌ات را بساز.</h1>
      <p>شروع با گوگل، برای ویدیوهایی که دوست داری دوباره ببینی.</p>
      <div dir="rtl">
        <SignUp
          routing="path"
          path="/sign-up"
          signInUrl="/sign-in"
          forceRedirectUrl="/"
        />
      </div>
    </main>
  );
}
