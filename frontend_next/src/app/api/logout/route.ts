/**
 * POST /api/logout
 *
 * Clears the auth cookie. Backend has no logout endpoint (JWTs are stateless),
 * so this is purely a browser-side state reset.
 */
import { clearAuthCookie } from "@/lib/auth";

export async function POST() {
  await clearAuthCookie();
  return Response.json({ ok: true });
}
