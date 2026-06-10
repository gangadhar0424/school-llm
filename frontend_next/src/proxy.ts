/**
 * Next.js 16 proxy (formerly middleware.ts).
 *
 * Cheap unauthenticated gate: if the auth cookie is missing on a protected
 * route, redirect to /login before any RSC rendering happens. The deeper
 * role-based check still happens inside each route's Server Component via
 * `requireRole()`.
 *
 * Doing the cookie-presence check here means logged-out users never pay
 * the cost of trying to hit FastAPI for /me on every navigation.
 */
import { NextResponse, type NextRequest } from "next/server";
import { AUTH_COOKIE } from "@/lib/auth";

const PROTECTED_PREFIXES = ["/student", "/teacher", "/admin"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isProtected = PROTECTED_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );
  if (!isProtected) return NextResponse.next();

  const token = request.cookies.get(AUTH_COOKIE)?.value;
  if (!token) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("from", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Match everything except Next internals and the public API auth surface.
  // The proxy only redirects when needed; matching everything else is fine.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|api/login|api/signup|api/logout|api/me).*)",
  ],
};
