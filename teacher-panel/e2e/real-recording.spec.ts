import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { createCourse, loginAsTeacher, unique } from "./helpers";

// Uses the dev backend's demo teacher (python scripts/seed_demo.py) — see playwright.real.config.ts
const BACKEND_DIR = path.resolve(__dirname, "../../backend");
const PYTHON = path.join(BACKEND_DIR, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const PUBLISH_SECONDS = Number(process.env.REAL_PUBLISH_SECONDS ?? 75);

type Check = {
  objects: { key: string; size: number; boxes: string[]; duration_seconds: number | null }[];
  session: { status: string; recording_status: string; recording_error: string | null; resulting_lesson_id: string | null };
  events: string[];
  failures: unknown[];
};

function check(sessionId: string): Check {
  const out = execFileSync(PYTHON, ["scripts/check_recording.py", sessionId], { cwd: BACKEND_DIR, encoding: "utf8" });
  return JSON.parse(out.trim().split("\n").pop()!);
}

// Through the page itself, exactly like the panel does (same-origin fetch, httpOnly cookies)
async function sessionStatus(page: Page, id: string) {
  return page.evaluate(async (sid) => (await fetch(`/api/bff/teacher/live-sessions/${sid}`)).json(), id);
}

async function syncLesson(page: Page, lessonId: string) {
  return page.evaluate(
    async (id) => (await fetch(`/api/bff/teacher/lessons/${id}/sync-status`, { method: "POST" })).json(),
    lessonId,
  );
}

test("real live lesson is recorded to MinIO and becomes a lesson", async ({ page }) => {
  await loginAsTeacher(page);
  const courseId = await createCourse(page, unique("Haqiqiy efir"));
  await page.getByTestId("tab-live").click();
  await page.getByLabel("Mavzu").fill("Haqiqiy yozuv sinovi");
  const now = new Date(Date.now() + 5 * 3600_000).toISOString().slice(0, 16); // Tashkent local time
  await page.getByLabel("Sana va vaqt").fill(now);
  await page.getByTestId("live-schedule").click();
  await page.getByTestId("live-row").first().getByTestId("live-open").click();
  await page.waitForURL(/\/live\/[0-9a-f-]{36}$/);
  const sessionId = page.url().split("/live/")[1];
  expect(courseId).toBeTruthy();

  // Start: fake camera + microphone, room, automatic recording
  await page.getByTestId("studio-start").click();
  await expect(page.getByTestId("toggle-mic")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("live-status")).toHaveText("Efirda");
  await expect(page.getByTestId("camera-preview")).toBeVisible();
  const started = await sessionStatus(page, sessionId);
  console.log("after start:", JSON.stringify(started));
  expect(started.recording_status).toBe("recording");

  // Screen share once during the lesson (fake UI picks the screen automatically)
  await page.getByTestId("toggle-screen").click();
  await page.waitForTimeout(5_000);
  await page.getByTestId("toggle-screen").click();

  console.log(`publishing for ${PUBLISH_SECONDS}s ...`);
  await page.waitForTimeout(PUBLISH_SECONDS * 1000);
  console.log("connection quality:", await page.getByTestId("connection-quality").innerText());

  await page.getByTestId("studio-end").click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Darsni tugatish" }).click();
  await expect(page.getByTestId("live-status")).toHaveText("Tugagan");

  // egress_ended -> lesson created -> imported (mock provider "encodes" for 60 s)
  let state: Check | null = null;
  for (let i = 0; i < 60; i++) {
    state = check(sessionId);
    if (!["recording", "uploading"].includes(state.session.recording_status)) break;
    await page.waitForTimeout(2_000);
  }
  console.log("after egress_ended:", JSON.stringify(state));
  expect(state!.failures).toEqual([]);
  expect(state!.session.recording_status).toBe("processing");
  expect(state!.session.resulting_lesson_id).toBeTruthy();

  // The raw recording really is in MinIO and is a real mp4
  const [mp4] = state!.objects;
  expect(mp4.key).toMatch(new RegExp(`^recordings/${sessionId}/.+\\.mp4$`));
  expect(mp4.size).toBeGreaterThan(100_000);
  expect(mp4.boxes).toEqual(expect.arrayContaining(["ftyp", "moov", "mdat"]));
  expect(mp4.duration_seconds!).toBeGreaterThan(PUBLISH_SECONDS * 0.6);

  // Video "ready" at the provider -> the unprotected mp4 must be deleted from MinIO
  const lessonId = state!.session.resulting_lesson_id!;
  for (let i = 0; i < 40; i++) {
    if ((await syncLesson(page, lessonId)).status === "ready") break;
    await page.waitForTimeout(3_000);
  }
  const final = check(sessionId);
  console.log("final:", JSON.stringify(final));
  expect(final.session.recording_status).toBe("ready");
  expect(final.objects).toEqual([]);
  expect(final.events).toEqual(expect.arrayContaining(["recording_started", "recording_imported", "recording_temp_file_deleted", "recording_ready"]));
});
