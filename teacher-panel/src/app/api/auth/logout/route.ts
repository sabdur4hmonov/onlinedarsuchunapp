import { NextResponse, type NextRequest } from "next/server";

import { callAsTeacher, errorJson } from "@/lib/server/bff";
import { clearSessionCookies, isSameOrigin } from "@/lib/server/session";

export async function POST(req: NextRequest) {
  if (!isSameOrigin(req)) return errorJson(403, "bad_origin", "So'rov rad etildi");
  // Revoke the session on the backend (best effort), then forget the cookies in any case
  await callAsTeacher(req, "/auth/logout", { method: "POST" }).catch(() => null);
  const res = new NextResponse(null, { status: 204 });
  clearSessionCookies(res);
  return res;
}
