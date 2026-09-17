import { ClerkProvider } from "@clerk/nextjs";
import { faIR } from "@clerk/localizations";
import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "حال‌خوب — آرشیو لحظه‌های خوب",
  description: "آرشیو شخصی ویدیوها، برای حسی که امروز می‌خواهی.",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "16x16 32x32 48x48" },
      { url: "/brand/mark.svg", type: "image/svg+xml", sizes: "any" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
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
            elements: { logoBox: { display: "none" } },
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
