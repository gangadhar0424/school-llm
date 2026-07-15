/**
 * POST /api/login
 *
 * Browser-facing login endpoint. Forwards credentials to FastAPI, then on
 * success:
 *   1. Sets the JWT into an httpOnly cookie (browser never sees it directly).
 *   2. Loads /api/auth/me to validate role match (the backend already does
 *      this for student/teacher accounts via its own role check, but admin
 *      mismatch slips through; do it here so the user always lands on a
 *      dashboard their account is actually allowed to access).
 *   3. Returns the user payload to the client so the login page can route
 *      to the right dashboard.
 */
import { backendFetch, decodeBackendError } from "@/lib/api";
import { setAuthCookie } from "@/lib/auth";
import type { LoginResponse, Role, User } from "@/lib/types";

const ALLOWED_ROLES: Role[] = ["super_admin", "admin", "teacher", "student"];

function prettyRole(role: string): string {
  if (role === "super_admin") return "Super Admin";
  if (role === "admin") return "Admin";
  if (role === "teacher") return "Teacher";
  if (role === "student") return "Student";
  return role.charAt(0).toUpperCase() + role.slice(1);
}

export async function POST(request: Request) {
  let body: { email?: string; password?: string; role?: string };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const email = (body.email || "").trim();
  const password = body.password || "";
  const role = (body.role || "student").toLowerCase();

  if (!email || !password) {
    return Response.json(
      { error: "Username and password are required." },
      { status: 400 }
    );
  }
  if (!ALLOWED_ROLES.includes(role as Role)) {
    return Response.json({ error: "Invalid role." }, { status: 400 });
  }

  // 1. Hit FastAPI /api/auth/login (public).
  const loginRes = await backendFetch("/api/auth/login", {
    method: "POST",
    json: { email, password, role },
  });
  if (!loginRes.ok) {
    const raw = await loginRes.json().catch(() => ({}));
    return Response.json(
      { error: decodeBackendError(raw) || "Login failed." },
      { status: loginRes.status }
    );
  }
  const login = (await loginRes.json()) as LoginResponse;
  const token = login.access_token;

  // 2. Validate /api/auth/me and double-check role.
  const meRes = await backendFetch("/api/auth/me", { token });
  if (!meRes.ok) {
    const raw = await meRes.json().catch(() => ({}));
    return Response.json(
      { error: decodeBackendError(raw) || "Session validation failed." },
      { status: meRes.status }
    );
  }
  const user = (await meRes.json()) as User;

  const actual = (user.role || "").toLowerCase();
  // Super admins live above the school role hierarchy; whichever tab the
  // user picked on the login page, we accept them and let homeForRole()
  // route them to /super-admin.
  if (actual === "super_admin") {
    await setAuthCookie(token);
    return Response.json({ user });
  }
  const effective = ALLOWED_ROLES.includes(actual as Role)
    ? actual
    : user.is_admin
      ? "admin"
      : "student";
  if (effective !== role) {
    return Response.json(
      {
        error:
          `This is a ${prettyRole(effective)} account. ` +
          `Please select ${prettyRole(effective)} and try again.`,
        actual_role: effective,
      },
      { status: 403 }
    );
  }

  // 3. Persist cookie + return the user so the client can route.
  await setAuthCookie(token);
  return Response.json({ user });
}
