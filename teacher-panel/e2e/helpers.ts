import { expect, type APIRequestContext, type Page } from "@playwright/test";

// Demo accounts from backend/scripts/seed_demo.py (test-only passwords)
export const TEACHER = { phone: "+998900000001", password: "Demo-Teacher-1" };
export const OTHER_TEACHER = { phone: "+998900000002", password: "Demo-Teacher-2" };
export const STUDENT = { phone: "+998901000001", password: "Demo-Student-1" };
export const STUDENT_2 = { phone: "+998901000002", password: "Demo-Student-2" };
export const BACKEND_URL = "http://127.0.0.1:8100";

export async function login(page: Page, account: { phone: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("Telefon raqam").fill(account.phone);
  await page.getByLabel("Parol").fill(account.password);
  await page.getByRole("button", { name: "Kirish" }).click();
}

export async function loginAsTeacher(page: Page, account = TEACHER) {
  await login(page, account);
  await expect(page).toHaveURL(/\/courses$/);
}

export function unique(prefix: string) {
  return `${prefix} ${Date.now().toString(36)}`;
}

export async function createCourse(page: Page, title: string): Promise<string> {
  await page.goto("/courses");
  await page.getByTestId("new-course").click();
  await page.getByLabel("Kurs nomi").fill(title);
  await page.getByRole("button", { name: "Yaratish" }).click();
  await page.getByTestId("course-card").filter({ hasText: title }).click();
  await expect(page.getByTestId("course-title")).toHaveText(title);
  return page.url().split("/courses/")[1].split("?")[0];
}

/** What the mobile app does: log in on a phone and confirm device binding. */
export async function bindStudentPhone(request: APIRequestContext, account: { phone: string; password: string }) {
  const deviceId = `e2e-phone-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const headers = { "X-Device-ID": deviceId };
  const login = await request.post(`${BACKEND_URL}/auth/login`, { data: account, headers });
  const body = await login.json();
  expect(body.status).toBe("device_binding_required");
  const bind = await request.post(`${BACKEND_URL}/auth/devices/bind`, {
    data: { binding_token: body.binding_token, device_name: "E2E Phone", platform: "android" },
    headers,
  });
  expect(bind.ok()).toBeTruthy();
  return deviceId;
}
