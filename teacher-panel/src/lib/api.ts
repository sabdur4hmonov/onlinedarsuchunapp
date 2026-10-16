import { t } from "@/lib/i18n";

/** Error from the backend, with its machine-readable code and Uzbek message. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public detail?: Record<string, unknown>,
  ) {
    super(message);
  }
}

function toError(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown })?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as Record<string, unknown>;
    return new ApiError(status, String(d.code ?? "error"), String(d.message ?? t.app.genericError), d);
  }
  return new ApiError(status, status === 422 ? "validation_error" : "error", t.app.genericError);
}

/**
 * Calls the backend THROUGH the panel server (/api/bff/...). The browser holds no tokens;
 * httpOnly cookies are attached automatically and only the panel server can read them.
 */
export async function api<T = unknown>(path: string, init: { method?: string; json?: unknown } = {}): Promise<T> {
  const res = await fetch(`/api/bff${path}`, {
    method: init.method ?? "GET",
    credentials: "same-origin",
    headers: init.json !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: init.json !== undefined ? JSON.stringify(init.json) : undefined,
    cache: "no-store",
  });
  if (res.status === 401) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.assign(`/login?next=${next}`);
    throw new ApiError(401, "unauthorized", t.app.genericError);
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw toError(res.status, body);
  return body as T;
}

export const fetcher = <T,>(path: string) => api<T>(path);
