import { SignIn } from "@clerk/nextjs";
export default function Page() {
  return (
    <main className="auth-page">
      <a className="brand" href="/">
        حال‌خوب<span>جایی برای دوباره حال خوب داشتن</span>
      </a>
      <h1>لحظه‌های خوبت، همیشه نزدیک.</h1>
      <p>با حساب گوگل وارد شو؛ آرشیو و دسته‌ها فقط برای خودت هستند.</p>
      <div dir="rtl">
        <SignIn
          routing="path"
          path="/sign-in"
          signUpUrl="/sign-up"
          forceRedirectUrl="/"
        />
      </div>
    </main>
  );
}
