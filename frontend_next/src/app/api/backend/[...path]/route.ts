/**
 * Catch-all proxy → FastAPI.
 *
 * Browser code calls `/api/backend/{anything}` and the cookie's JWT is
 * attached server-side before forwarding to FastAPI's `/api/{anything}`.
 * That keeps the token in an httpOnly cookie (no XSS-readable storage)
 * while letting us reuse the entire backend surface without rewriting
 * a route handler per endpoint.
 *
 * Multipart uploads pass through transparently because we forward the
 * raw request body.
 */
import { backendFetch } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";

type RouteCtx = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, ctx: RouteCtx, method: string) {
  const { path } = await ctx.params;
  const token = await getAuthToken();
  if (!token) {
    return Response.json({ error: "not_authenticated" }, { status: 401 });
  }

  const backendPath = "/api/" + path.join("/");
  const url = new URL(request.url);
  const query: Record<string, string> = {};
  url.searchParams.forEach((v, k) => {
    query[k] = v;
  });

  // Forward body verbatim when present. fetch handles multipart boundaries
  // correctly when we hand it a FormData (vs. cloned ReadableStream which
  // Node's undici can choke on for multipart).
  const contentType = request.headers.get("content-type") || "";
  let json: unknown;
  let formData: FormData | undefined;
  if (
    method !== "GET" &&
    method !== "DELETE" &&
    method !== "HEAD" &&
    request.body
  ) {
    if (contentType.includes("multipart/form-data")) {
      formData = await request.formData();
    } else if (contentType.includes("application/json")) {
      const text = await request.text();
      json = text ? JSON.parse(text) : undefined;
    } else {
      const text = await request.text();
      json = text;
    }
  }

  const upstream = await backendFetch(backendPath, {
    method,
    token,
    json,
    formData,
    query,
  });

  // Stream back exactly what FastAPI sent.
  const body = await upstream.arrayBuffer();
  return new Response(body, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("content-type") || "application/json",
    },
  });
}

export const GET = (req: Request, ctx: RouteCtx) => proxy(req, ctx, "GET");
export const POST = (req: Request, ctx: RouteCtx) => proxy(req, ctx, "POST");
export const PUT = (req: Request, ctx: RouteCtx) => proxy(req, ctx, "PUT");
export const PATCH = (req: Request, ctx: RouteCtx) => proxy(req, ctx, "PATCH");
export const DELETE = (req: Request, ctx: RouteCtx) =>
  proxy(req, ctx, "DELETE");
