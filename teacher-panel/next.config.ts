import type { NextConfig } from "next";

const isProd = process.env.NODE_ENV === "production";

// Static security headers for every response (pages AND /api routes).
// The Content-Security-Policy needs a fresh nonce per request, so it is set in src/proxy.ts.
const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  {
    key: "Permissions-Policy",
    // Camera/microphone/screen only for this site (live lessons), nothing else
    value: "camera=(self), microphone=(self), display-capture=(self), geolocation=(), payment=(), usb=()",
  },
  // HSTS only in production: on http://localhost it is pointless, and it is hard to undo
  ...(isProd ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" }] : []),
];

const nextConfig: NextConfig = {
  // Nonce-based CSP requires every page to be rendered per request; Partial Prerendering
  // (part of Cache Components) cannot carry a nonce, so both stay off for this dashboard.
  cacheComponents: false,
  partialPrefetching: false,
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
