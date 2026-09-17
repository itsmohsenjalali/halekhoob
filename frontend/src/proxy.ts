import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
const publicRoute = createRouteMatcher([
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/healthz",
]);
export default clerkMiddleware(async (auth, request) => {
  const publicUrl = process.env.APP_PUBLIC_URL;
  if (publicUrl && request.nextUrl.pathname !== "/healthz") {
    const canonical = new URL(publicUrl);
    if (request.headers.get("host") !== canonical.host) {
      canonical.pathname = request.nextUrl.pathname;
      canonical.search = request.nextUrl.search;
      return NextResponse.redirect(canonical, 307);
    }
  }
  if (!publicRoute(request) && !request.nextUrl.pathname.startsWith("/api/v1/"))
    await auth.protect();
});
export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|map)).*)",
  ],
};
