/**
 * PUT /api/user/theme  → forwards to FastAPI /api/auth/theme.
 *
 * Special-cased outside the catch-all proxy because the proxy mounts at
 * /api/backend/*; theme switching is convenient to call from anywhere
 * via the unprefixed /api/user/theme.
 */
import { proxyJson } from "@/lib/api";

export async function PUT(request: Request) {
  const body = await request.json().catch(() => ({}));
  return proxyJson("/api/auth/theme", { method: "PUT", json: body });
}
