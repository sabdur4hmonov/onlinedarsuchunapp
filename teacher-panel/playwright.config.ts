import fs from "node:fs";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/*
 * E2E tests in MOCK mode: a separate backend on :8100 with its own "_e2e" database
 * (wiped and re-seeded on every run), no LiveKit / VdoCipher / S3 keys, and a
 * production build of the panel on :3100. The developer's dev servers stay untouched.
 */

const BACKEND_DIR = path.resolve(__dirname, "../backend");
const PYTHON = path.join(BACKEND_DIR, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
export const BACKEND_URL = "http://127.0.0.1:8100";
const PANEL_URL = "http://localhost:3100";

function e2eDatabaseUrl(): string {
  if (process.env.E2E_DATABASE_URL) return process.env.E2E_DATABASE_URL;
  const env = fs.readFileSync(path.join(BACKEND_DIR, ".env"), "utf8");
  const url = env.match(/^DATABASE_URL=(.+)$/m)?.[1]?.trim();
  if (!url) throw new Error("DATABASE_URL not found in backend/.env");
  return url.replace(/\/[^/]+$/, "/course_platform_e2e");
}

export default defineConfig({
  testDir: "./e2e",
  testIgnore: /real-recording/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  use: { baseURL: PANEL_URL, trace: "retain-on-failure", locale: "uz-UZ", timezoneId: "Asia/Tashkent" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `"${PYTHON}" scripts/prepare_e2e_db.py && "${PYTHON}" -m uvicorn app.main:app --host 127.0.0.1 --port 8100`,
      cwd: BACKEND_DIR,
      url: `${BACKEND_URL}/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        DATABASE_URL: e2eDatabaseUrl(),
        // Empty values override backend/.env -> every external service is mocked
        VDOCIPHER_API_SECRET: "",
        LIVEKIT_URL: "",
        LIVEKIT_API_KEY: "",
        LIVEKIT_API_SECRET: "",
        RECORDINGS_S3_ACCESS_KEY: "",
        RECORDINGS_S3_SECRET_KEY: "",
        MOCK_VIDEO_UPLOAD_URL: `${BACKEND_URL}/dev/mock-video-upload`,
        CORS_ALLOWED_ORIGINS: PANEL_URL,
        TRUSTED_PROXY_IPS: "127.0.0.1",
        LOGIN_RATE_LIMIT_ATTEMPTS: "100",
      },
    },
    {
      command: "npm run build && npm run start -- -p 3100",
      url: `${PANEL_URL}/login`,
      timeout: 300_000,
      reuseExistingServer: false,
      env: {
        BACKEND_URL,
        PANEL_ORIGIN: PANEL_URL,
        COOKIE_SECURE: "true",
        CSP_CONNECT_SRC: BACKEND_URL,
      },
    },
  ],
});
