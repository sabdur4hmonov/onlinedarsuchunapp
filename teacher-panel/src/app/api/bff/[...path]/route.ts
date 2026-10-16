import type { NextRequest } from "next/server";

import { callAsTeacher, errorJson } from "@/lib/server/bff";
import { isSameOrigin } from "@/lib/server/session";

/*
 * Browser -> /api/bff/<path> -> backend /<path>, as the logged-in teacher.
 * Only teacher endpoints are reachable through here; tokens never reach the browser.
 */

const SEGMENT = /^[A-Za-z0-9_-]{1,64}$/;
const MAX_BODY_BYTES = 256 * 1024;

function allowed(path: string[]): boolean {
  if (!path.every((s) => SEGMENT.test(s))) return false; // no "..", no encoded slashes
  return path[0] === "teacher" || (path.length === 2 && path[0] === "auth" && path[1] === "me");
}

async function handle(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  if (!allowed(path)) return errorJson(404, "not_found");
  if (req.method !== "GET" && !isSameOrigin(req)) return errorJson(403, "bad_origin", "So'rov rad etildi");

  const init: RequestInit = { method: req.method };
  if (req.method !== "GET" && req.method !== "DELETE") {
    const body = await req.text();
    if (body.length > MAX_BODY_BYTES) return errorJson(413, "body_too_large");
    if (body) {
      init.body = body;
      init.headers = { "Content-Type": "application/json" };
    }
  }
  const query = req.nextUrl.searchParams.toString();
  return callAsTeacher(req, `/${path.join("/")}${query ? `?${query}` : ""}`, init);
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
