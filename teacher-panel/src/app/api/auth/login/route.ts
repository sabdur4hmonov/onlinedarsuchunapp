import { NextResponse, type NextRequest } from "next/server";

import { errorJson } from "@/lib/server/bff";
import {
  backendFetch,
  clientIp,
  getOrCreateDeviceId,
  isSameOrigin,
  setDeviceCookie,
  setSessionCookies,
  type Tokens,
} from "@/lib/server/session";

const TEACHER_ONLY = "Bu panel faqat o'qituvchilar uchun";

export async function POST(req: NextRequest) {
  if (!isSameOrigin(req)) return errorJson(403, "bad_origin", "So'rov rad etildi");

  let phone: unknown, password: unknown;
  try {
    ({ phone, password } = await req.json());
  } catch {
    return errorJson(400, "invalid_body");
  }
  if (typeof phone !== "string" || typeof password !== "string" || !phone || !password || password.length > 128) {
    return errorJson(400, "invalid_body", "Telefon raqam va parolni kiriting");
  }

  const { deviceId, isNew } = getOrCreateDeviceId(req);
  const ip = clientIp(req);
  const withDevice = (res: NextResponse) => {
    if (isNew) setDeviceCookie(res, deviceId);
    return res;
  };

  let login: Response;
  try {
    login = await backendFetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone, password }),
      deviceId,
      ip,
    });
  } catch {
    return withDevice(errorJson(503, "backend_unavailable", "Server vaqtincha ishlamayapti"));
  }
  const body = await login.json().catch(() => null);
  if (!login.ok) {
    // 401 wrong credentials, 422 bad phone format, 429 rate limit: pass the backend's message on
    const detail = body?.detail;
    const code = typeof detail?.code === "string" ? detail.code : "login_failed";
    const message = typeof detail?.message === "string" ? detail.message : "Telefon raqam yoki parolni tekshiring";
    return withDevice(errorJson(login.status === 422 ? 400 : login.status, code, message));
  }

  // Teachers never need device binding. "device_binding_required" means a student account:
  // refuse without binding anything (the student's own devices stay untouched).
  if (body?.status !== "ok") return withDevice(errorJson(403, "teacher_only", TEACHER_ONLY));

  const tokens = body as Tokens;
  const me = await backendFetch("/auth/me", { accessToken: tokens.access_token, deviceId, ip });
  const user = me.ok ? await me.json() : null;
  if (user?.role !== "teacher") {
    await backendFetch("/auth/logout", { method: "POST", accessToken: tokens.access_token, deviceId, ip }).catch(() => {});
    return withDevice(errorJson(403, "teacher_only", TEACHER_ONLY));
  }

  const res = NextResponse.json({ user: { id: user.id, full_name: user.full_name, phone: user.phone } });
  setSessionCookies(res, tokens);
  return withDevice(res);
}
