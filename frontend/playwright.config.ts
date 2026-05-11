import { defineConfig, devices } from "@playwright/test";

const FRONTEND_PORT = Number(process.env.FRONTEND_PORT || 3000);
const BASE_URL = process.env.E2E_BASE_URL || `http://localhost:${FRONTEND_PORT}`;

export default defineConfig({
  testDir: "./tests",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    headless: true,
    viewport: { width: 1920, height: 1080 },
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
