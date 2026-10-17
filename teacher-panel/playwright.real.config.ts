import { defineConfig, devices } from "@playwright/test";

/*
 * REAL live-recording test (not part of `npm run test:e2e`). Needs, already running:
 *   - cd backend && docker compose --profile live up -d      (LiveKit, Egress, Redis, MinIO)
 *   - backend on :8000 with the real backend/.env (LiveKit + MinIO configured)
 *     and MOCK_VIDEO_PROCESSING_SECONDS=60 so the raw mp4 stays in MinIO long enough to inspect
 *   - panel on :3000 (npm run dev)
 * Run: npx playwright test -c playwright.real.config.ts
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: /real-recording\.spec\.ts/,
  workers: 1,
  retries: 0,
  timeout: 6 * 60_000,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    timezoneId: "Asia/Tashkent",
    permissions: ["camera", "microphone"],
    launchOptions: {
      // Chromium's built-in fake camera (moving test pattern) and microphone (beeps)
      args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
