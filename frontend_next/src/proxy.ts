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
  // Skip Next internals AND every /api/* route. The proxy only gates
  // RSC navigations to protected pages; route handlers already check the
  // cookie themselves (via getAuthToken / getCurrentUser). Running the
  // middleware on every API call added measurable overhead per request
  // since each browser navigation triggers a handful of /api/backend/*
  // requests from React Query for usage, notifications, chat, etc.
  matcher: ["/((?!_next|api|favicon.ico).*)"],
};
