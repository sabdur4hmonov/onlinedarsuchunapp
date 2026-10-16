import { expect, test } from "@playwright/test";

import {
  bindStudentPhone,
  createCourse,
  login,
  loginAsTeacher,
  OTHER_TEACHER,
  STUDENT,
  STUDENT_2,
  TEACHER,
  unique,
} from "./helpers";

test.describe("auth", () => {
  test("pages require login", async ({ page }) => {
    await page.goto("/courses");
    await expect(page).toHaveURL(/\/login\?next=%2Fcourses/);
  });

  test("teacher logs in; tokens are invisible to page JavaScript", async ({ page, context }) => {
    await loginAsTeacher(page);
    await expect(page.getByRole("heading", { name: "Kurslar" })).toBeVisible();

    const visible = await page.evaluate(() => ({
      cookie: document.cookie,
      local: Object.keys(localStorage),
      session: Object.keys(sessionStorage),
    }));
    expect(visible.cookie).not.toContain("od_");
    expect(visible.local).toEqual([]);
    expect(visible.session).toEqual([]);

    const cookies = await context.cookies();
    const session = cookies.filter((c) => c.name.includes("od_"));
    expect(session.map((c) => c.name).sort()).toEqual(["__Host-od_at", "__Host-od_did", "__Host-od_rt"]);
    for (const c of session) {
      expect(c.httpOnly).toBe(true);
      expect(c.secure).toBe(true);
      expect(c.sameSite).toBe("Strict");
    }

    await page.getByTestId("logout").click();
    await expect(page).toHaveURL(/\/login/);
    await page.goto("/courses");
    await expect(page).toHaveURL(/\/login/);
  });

  test("student cannot enter the panel", async ({ page, context }) => {
    await login(page, STUDENT_2);
    await expect(page.getByTestId("login-error")).toHaveText("Bu panel faqat o'qituvchilar uchun");
    await expect(page).toHaveURL(/\/login/);
    expect((await context.cookies()).filter((c) => c.name.includes("od_rt"))).toEqual([]);
  });

  test("wrong password shows the backend message", async ({ page }) => {
    await login(page, { phone: TEACHER.phone, password: "wrong-password" });
    await expect(page.getByTestId("login-error")).toHaveText("Telefon raqam yoki parol noto'g'ri");
  });

  test("security headers", async ({ page }) => {
    const res = await page.goto("/login");
    const headers = res!.headers();
    expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
    expect(headers["content-security-policy"]).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["x-powered-by"]).toBeUndefined();
  });
});

test.describe("courses", () => {
  test("create and edit a course", async ({ page }) => {
    await loginAsTeacher(page);
    const title = unique("Fizika");
    await createCourse(page, title);

    await page.getByTestId("edit-course").click();
    await page.getByLabel("Kurs nomi").fill(`${title} (yangi)`);
    await page.getByRole("button", { name: "Saqlash" }).click();
    await expect(page.getByTestId("course-title")).toHaveText(`${title} (yangi)`);
  });

  test("another teacher cannot open the course", async ({ page, browser }) => {
    await loginAsTeacher(page);
    const courseId = await createCourse(page, unique("Maxfiy kurs"));

    const other = await browser.newPage();
    await loginAsTeacher(other, OTHER_TEACHER);
    await other.goto(`/courses/${courseId}`);
    await expect(other.getByText("Kurs topilmadi")).toBeVisible();
    await other.close();
  });
});

test.describe("students", () => {
  test("add a student, reset their device, remove them", async ({ page, request }) => {
    await bindStudentPhone(request, STUDENT);
    await loginAsTeacher(page);
    await createCourse(page, unique("Kimyo"));

    await page.getByLabel("O'quvchi qo'shish").fill("90 100 00 01");
    await page.getByTestId("add-student").click();
    const row = page.getByTestId("student-row").filter({ hasText: STUDENT.phone });
    await expect(row).toBeVisible();

    // Device dialog -> reset with confirmation
    await row.getByTestId("student-devices").click();
    const device = page.getByTestId("device-row").filter({ hasText: "E2E Phone" }).filter({ hasText: "Faol" });
    await expect(device.first()).toBeVisible();
    await device.first().getByTestId("device-reset").click();
    await expect(page.getByRole("alertdialog")).toContainText("Davom etasizmi?");
    await page.getByRole("alertdialog").getByRole("button", { name: "Qurilmani reset qilish" }).click();
    await expect(page.getByText("Qurilma reset qilindi")).toBeVisible();
    await expect(page.getByTestId("device-row").filter({ hasText: "Faol" })).toHaveCount(0);
    await page.keyboard.press("Escape");

    // The reset shows up in the course journal
    await page.getByTestId("tab-events").click();
    await expect(page.locator('[data-event-type="device_reset"]').first()).toBeVisible();

    // Remove from the course
    await page.getByTestId("tab-students").click();
    await row.getByTestId("student-remove").click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Kursdan chiqarish" }).click();
    await expect(page.getByTestId("student-row")).toHaveCount(0);
  });

  test("unknown phone shows an error", async ({ page }) => {
    await loginAsTeacher(page);
    await createCourse(page, unique("Tarix"));
    await page.getByLabel("O'quvchi qo'shish").fill("+998 99 999 99 99");
    await page.getByTestId("add-student").click();
    await expect(page.getByText("Bu raqam bilan o'quvchi topilmadi")).toBeVisible();
  });
});

test.describe("video lessons", () => {
  test("create lessons, reorder by drag and drop, upload a video, delete", async ({ page }) => {
    await loginAsTeacher(page);
    await createCourse(page, unique("Ingliz tili"));
    await page.getByTestId("tab-lessons").click();

    for (const title of ["Birinchi dars", "Ikkinchi dars"]) {
      await page.getByPlaceholder("Dars nomi").fill(title);
      await page.getByTestId("new-lesson").click();
      await expect(page.getByTestId("lesson-title").filter({ hasText: title })).toBeVisible();
    }
    await expect(page.getByTestId("lesson-title")).toHaveText(["Birinchi dars", "Ikkinchi dars"]);

    // Drag "Ikkinchi" above "Birinchi"
    const handles = page.getByTestId("lesson-drag");
    const from = await handles.nth(1).boundingBox();
    const to = await handles.nth(0).boundingBox();
    await page.mouse.move(from!.x + from!.width / 2, from!.y + from!.height / 2);
    await page.mouse.down();
    await page.mouse.move(to!.x + to!.width / 2, to!.y - 10, { steps: 15 });
    await page.mouse.up();
    await expect(page.getByText("Tartib saqlandi")).toBeVisible();
    await expect(page.getByTestId("lesson-title")).toHaveText(["Ikkinchi dars", "Birinchi dars"]);
    await page.reload();
    await expect(page.getByTestId("lesson-title")).toHaveText(["Ikkinchi dars", "Birinchi dars"]);

    // Direct upload with a progress bar (mock provider), then status "Tayyor"
    const first = page.getByTestId("lesson-row").first();
    await first.getByTestId("lesson-file").setInputFiles({
      name: "dars.mp4",
      mimeType: "video/mp4",
      buffer: Buffer.alloc(8 * 1024 * 1024),
    });
    await expect(page.getByText("Video yuklandi, qayta ishlanmoqda")).toBeVisible({ timeout: 30_000 });
    await expect(first.getByTestId("lesson-status")).toHaveText("Tayyor");

    // Delete with confirmation
    await first.getByTestId("lesson-delete").click();
    await page.getByRole("alertdialog").getByRole("button", { name: "O'chirish" }).click();
    await expect(page.getByTestId("lesson-title")).toHaveText(["Birinchi dars"]);
  });
});

test.describe("live lessons", () => {
  test("schedule, see status, open studio, cancel", async ({ page }) => {
    await loginAsTeacher(page);
    await createCourse(page, unique("Geometriya"));
    await page.getByTestId("tab-live").click();

    await page.getByLabel("Mavzu").fill("Uchburchaklar");
    await page.getByLabel("Sana va vaqt").fill("2030-05-01T15:00");
    await page.getByTestId("live-schedule").click();
    const row = page.getByTestId("live-row").filter({ hasText: "Uchburchaklar" });
    await expect(row).toContainText("2030-05-01 15:00");
    await expect(row.getByTestId("live-status")).toHaveText("Rejalashtirilgan");

    await row.getByTestId("live-open").click();
    await expect(page.getByTestId("studio-start")).toBeVisible();
    await page.getByText("Kursga qaytish").click();

    await row.getByTestId("live-cancel").click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Bekor qilish" }).last().click();
    await expect(row.getByTestId("live-status")).toHaveText("Bekor qilingan");
  });
});
