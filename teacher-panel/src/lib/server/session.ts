import "server-only";

import { createHash, randomUUID } from "node:crypto";
import type { NextRequest, NextResponse } from "next/server";

import { config, DEVICE_ID_MAX_AGE, REFRESH_TOKEN_MAX_AGE } from "./config";
import { COOKIE } from "./cookie-names";

export { COOKIE };

/*
 * BFF session: the browser never sees our API tokens.
 *  - access token  -> httpOnly cookie, lives ~15 min
 *  - refresh token -> httpOnly cookie, 30 days
 *  - device id     -> httpOnly cookie, stable per browser (backend requires X-Device-ID)
 * All cookies: Secure, SameSite=Strict, Path=/, "__Host-" prefix (no Domain, cannot be
 * overwritten by subdomains). JavaScript in the page cannot read any of them.
 */

export type Tokens = { access_token: string; refresh_token: string; expires_in: number };

const baseCookie = { httpOnly: true, secure: config.cookieSecure, sameSite: "strict" as const, path: "/" };

export function setSessionCookies(res: NextResponse, tokens: Tokens) {
  // Expire the access cookie a bit early so we refresh before the backend says 401
  res.cookies.set(COOKIE.access, tokens.access_token, { ...baseCookie, maxAge: Math.max(tokens.expires_in - 30, 30) });
  res.cookies.set(COOKIE.refresh, tokens.refresh_token, { ...baseCookie, maxAge: REFRESH_TOKEN_MAX_AGE });
}

export function clearSessionCookies(res: NextResponse) {
  res.cookies.set(COOKIE.access, "", { ...baseCookie, maxAge: 0 });
  res.cookies.set(COOKIE.refresh, "", { ...baseCookie, maxAge: 0 });
}

/** Stable per-browser device ID (creates one if missing). */
export function getOrCreateDeviceId(req: NextRequest): { deviceId: string; isNew: boolean } {
  const existing = req.cookies.get(COOKIE.device)?.value;
  if (existing && /^panel-[0-9a-f-]{36}$/.test(existing)) return { deviceId: existing, isNew: false };
  return { deviceId: `panel-${randomUUID()}`, isNew: true };
}

export function setDeviceCookie(res: NextResponse, deviceId: string) {
  res.cookies.set(COOKIE.device, deviceId, { ...baseCookie, maxAge: DEVICE_ID_MAX_AGE });
}

/**
 * Browser's IP for the backend's audit log and rate limits.
 * Next.js only ADDS X-Forwarded-For when it is missing, so in production the panel must sit
 * behind a reverse proxy that OVERWRITES it with the real client address (see README).
 */
export function clientIp(req: NextRequest): string {
  const forwarded = req.headers.get("x-forwarded-for") ?? "";
  const last = forwarded.split(",").pop()?.trim() ?? "";
  return last.replace(/^::ffff:/, "").slice(0, 45) || "unknown";
}

/** CSRF guard for state-changing requests: SameSite=Strict + exact Origin match. */
export function isSameOrigin(req: NextRequest): boolean {
  const origin = req.headers.get("origin");
  const expected = config.panelOrigin || req.nextUrl.origin;
  if (origin !== expected) return false;
  const site = req.headers.get("sec-fetch-site");
  return site === null || site === "same-origin";
}

export async function backendFetch(
  path: string,
  init: RequestInit & { accessToken?: string; deviceId: string; ip: string },
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("X-Device-ID", init.deviceId);
  headers.set("X-Forwarded-For", init.ip);
  headers.set("Accept", "application/json");
  if (init.accessToken) headers.set("Authorization", `Bearer ${init.accessToken}`);
  return fetch(`${config.backendUrl}${path}`, { ...init, headers, cache: "no-store", redirect: "manual" });
}

/*
 * Single-flight refresh.
 * The backend treats a second use of a rotated refresh token as theft and logs the teacher
 * out everywhere. Several panel requests may arrive with the same (old) refresh cookie at
 * once, or shortly after a refresh, before the browser stored the new cookie. So:
 *  - only ONE request per refresh token goes to the backend;
 *  - its result is shared with every request carrying that token for 60 s.
 * Note: this state lives in this Node process. Running several panel instances needs a
 * shared store (e.g. Redis) or sticky sessions.
 */
/** "invalid" = the backend rejected the refresh token: the session is over. */
export type RefreshResult = Tokens | "invalid";

export class BackendUnavailable extends Error {}

type Flight = { promise: Promise<RefreshResult>; until: number };
const globalStore = globalThis as unknown as { __odRefreshFlights?: Map<string, Flight> };
const flights = (globalStore.__odRefreshFlights ??= new Map<string, Flight>());
const SHARE_RESULT_MS = 60_000;

/** Throws BackendUnavailable on network errors / 5xx (that must NOT log the teacher out). */
export function refreshTokens(refreshToken: string, deviceId: string, ip: string): Promise<RefreshResult> {
  const key = createHash("sha256").update(refreshToken).digest("hex");
  const now = Date.now();
  for (const [k, f] of flights) if (f.until < now) flights.delete(k);

  const existing = flights.get(key);
  if (existing) return existing.promise;

  const promise = backendFetch("/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
    deviceId,
    ip,
  }).then(
    async (r): Promise<RefreshResult> => {
      if (r.ok) return (await r.json()) as Tokens;
      if (r.status >= 500) throw new BackendUnavailable(`refresh: HTTP ${r.status}`);
      return "invalid";
    },
    () => {
      throw new BackendUnavailable("refresh: backend unreachable");
    },
  );
  flights.set(key, { promise, until: now + SHARE_RESULT_MS });
  // A temporary outage must not be remembered: let the next request try again
  promise.catch(() => flights.delete(key));
  return promise;
}
