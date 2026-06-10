/**
 * POST /api/signup
 *
 * Forwards the signup body to FastAPI as-is. We don't auto-login on
 * success — explicit re-login lets us reuse the role-check path in
 * /api/login instead of duplicating it here.
 */
import { backendFetch, decodeBackendError } from "@/lib/api";

export async function POST(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const res = await backendFetch("/api/auth/signup", {
    method: "POST",
    json: body,
  });
  if (!res.ok) {
    const raw = await res.json().catch(() => ({}));
    return Response.json(
      { error: decodeBackendError(raw) || "Signup failed." },
      { status: res.status }
    );
  }
  const created = await res.json();
  return Response.json({ user: created });
}
