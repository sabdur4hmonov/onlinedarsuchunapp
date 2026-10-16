import { NextResponse, type NextRequest } from "next/server";

import { COOKIE } from "@/lib/server/cookie-names";

/*
 * Runs before every page:
 * 1. Content-Security-Policy with a fresh nonce (Next.js attaches it to its own scripts).
 * 2. Pages need a session cookie; otherwise -> /login.
 */

const isDev = process.env.NODE_ENV === "development";
// Extra places the browser may connect to, space-separated: the LiveKit server (ws/wss)
// and the video upload host (VdoCipher's storage, or the backend's mock upload in dev).
const extraConnectSrc = (process.env.CSP_CONNECT_SRC ?? "").trim();

function contentSecurityPolicy(nonce: string): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    // Inline style ATTRIBUTES (used by UI components) cannot carry a nonce; they cannot run code
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "media-src 'self' blob: mediastream:",
    "font-src 'self'",
    `connect-src 'self' ${extraConnectSrc}`.trim(),
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(isDev ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const isLogin = pathname === "/login";
  if (!isLogin && !request.cookies.get(COOKIE.refresh)) {
    const url = new URL("/login", request.url);
    if (pathname !== "/") url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }

  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = contentSecurityPolicy(nonce);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
