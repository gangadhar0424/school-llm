/**
 * GET /api/ws-token
 *
 * Returns the JWT and the WebSocket URL so the browser can open a
 * realtime connection directly to FastAPI. The JWT lives in an httpOnly
 * cookie that the browser can't read directly; this handler runs
 * server-side, reads the cookie, and hands the token out.
 *
 * Security note: the token leaves the httpOnly cookie when we serve this
 * response, but only into the browser's JS memory — never localStorage,
 * never the URL bar (the URL the browser builds for the WebSocket has
 * the token in the query string, but that URL is constructed and used
 * client-side in JS, never navigated to). Same exposure shape as Slack,
 * Discord, etc.
 */
import { getAuthToken } from "@/lib/auth";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

function backendToWsUrl(backendUrl: string): string {
  // http://host:port → ws://host:port; https → wss.
  return backendUrl.replace(/^http(s?):\/\//, (_m, s) => `ws${s}://`);
}

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || backendToWsUrl(BACKEND_URL);

export async function GET() {
  const token = await getAuthToken();
  if (!token) {
    return Response.json({ error: "not_authenticated" }, { status: 401 });
  }
  return Response.json({
    token,
    url: `${WS_BASE}/ws`,
  });
}
