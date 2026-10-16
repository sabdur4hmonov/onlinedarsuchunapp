import "server-only";

import { NextResponse, type NextRequest } from "next/server";

import {
  BackendUnavailable,
  backendFetch,
  clearSessionCookies,
  clientIp,
  COOKIE,
  getOrCreateDeviceId,
  refreshTokens,
  setSessionCookies,
  type Tokens,
} from "./session";

export function errorJson(status: number, code: string, message?: string) {
  return NextResponse.json({ detail: { code, message: message ?? code } }, { status });
}

/**
 * Calls the backend as the logged-in teacher.
 * Uses the access cookie; if it is missing/expired, refreshes ONCE (single-flight) and retries.
 * Writes rotated tokens into the response cookies, or clears them when the session is over.
 */
export async function callAsTeacher(
  req: NextRequest,
  path: string,
  init: RequestInit = {},
): Promise<NextResponse> {
  const refreshToken = req.cookies.get(COOKIE.refresh)?.value;
  const { deviceId, isNew } = getOrCreateDeviceId(req);
  if (!refreshToken || isNew) {
    const res = errorJson(401, "unauthorized", "Qaytadan kiring");
    clearSessionCookies(res);
    return res;
  }
  const ip = clientIp(req);
  let accessToken = req.cookies.get(COOKIE.access)?.value;
  let refreshed: Tokens | null = null;

  const refresh = async (): Promise<NextResponse | null> => {
    try {
      const result = await refreshTokens(refreshToken, deviceId, ip);
      if (result === "invalid") {
        const res = errorJson(401, "session_expired", "Sessiya tugadi, qaytadan kiring");
        clearSessionCookies(res);
        return res;
      }
      refreshed = result;
      accessToken = result.access_token;
      return null;
    } catch (e) {
      if (e instanceof BackendUnavailable) return errorJson(503, "backend_unavailable", "Server vaqtincha ishlamayapti");
      throw e;
    }
  };

  if (!accessToken) {
    const failed = await refresh();
    if (failed) return failed;
  }

  let upstream: Response;
  try {
    upstream = await backendFetch(path, { ...init, accessToken, deviceId, ip });
    if (upstream.status === 401 && !refreshed) {
      const failed = await refresh();
      if (failed) return failed;
      upstream = await backendFetch(path, { ...init, accessToken, deviceId, ip });
    }
  } catch {
    return errorJson(503, "backend_unavailable", "Server vaqtincha ishlamayapti");
  }

  const body = upstream.status === 204 ? null : await upstream.text();
  const res = new NextResponse(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json", "Cache-Control": "no-store" },
  });
  if (refreshed) setSessionCookies(res, refreshed);
  if (upstream.status === 401) clearSessionCookies(res);
  return res;
}
