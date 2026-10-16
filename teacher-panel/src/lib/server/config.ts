import "server-only";

/** Server-side settings from .env.local. Never imported by browser code. */
export const config = {
  // Where the FastAPI backend listens (reached from the panel SERVER, not from browsers)
  backendUrl: (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, ""),
  // Secure cookies. Browsers accept them on http://localhost too; set "false" only for
  // testing over plain http from another device (e.g. a LAN IP).
  cookieSecure: process.env.COOKIE_SECURE !== "false",
  // Public origin of this panel, e.g. https://panel.example.uz (for CSRF Origin checks).
  // Empty = the request's own origin.
  panelOrigin: (process.env.PANEL_ORIGIN ?? "").replace(/\/$/, ""),
};

export const REFRESH_TOKEN_MAX_AGE = 30 * 24 * 3600;
export const DEVICE_ID_MAX_AGE = 2 * 365 * 24 * 3600;
