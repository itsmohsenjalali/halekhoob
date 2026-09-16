import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
const publicRoute = createRouteMatcher([
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/healthz",
]);
export default clerkMiddleware(async (auth, request) => {
  if (!publicRoute(request) && !request.nextUrl.pathname.startsWith("/api/v1/"))
    await auth.protect();
});
export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|map)).*)",
  ],
};
