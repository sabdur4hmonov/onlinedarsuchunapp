// Cookie NAMES only (not secret). Kept free of "server-only" so src/proxy.ts can import it.
// "__Host-" prefix: the browser accepts the cookie only with Secure, Path=/ and no Domain.
const prefix = process.env.COOKIE_SECURE === "false" ? "" : "__Host-";

export const COOKIE = {
  access: `${prefix}od_at`,
  refresh: `${prefix}od_rt`,
  device: `${prefix}od_did`,
} as const;
