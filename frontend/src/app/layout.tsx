import { ClerkProvider } from "@clerk/nextjs";
import { faIR } from "@clerk/localizations";
import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "حال‌خوب — آرشیو لحظه‌های خوب",
  description: "آرشیو شخصی ویدیوها، برای حسی که امروز می‌خواهی.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl">
      <body>
        <ClerkProvider
          localization={faIR}
          signInUrl="/sign-in"
          signUpUrl="/sign-up"
          signInFallbackRedirectUrl="/"
          signUpFallbackRedirectUrl="/"
          appearance={{
            variables: {
              colorPrimary: "#68784d",
              fontFamily: "Vazirmatn, sans-serif",
              borderRadius: "14px",
            },
          }}
        >
          {children}
        </ClerkProvider>
      </body>
    </html>
  );
}
