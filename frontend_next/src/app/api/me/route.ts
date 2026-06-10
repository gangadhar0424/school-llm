/**
 * GET /api/me
 *
 * Returns the current user payload, or 401 if not logged in.
 * Used by client components that need user info without a full reload.
 */
import { getCurrentUser } from "@/lib/auth";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) {
    return Response.json({ error: "not_authenticated" }, { status: 401 });
  }
  return Response.json({ user });
}
