import { defineConfig, devices } from "@playwright/test";

/**
 * Phase 9-C UI E2E. The suite assumes the backend (:8000) and Next dev
 * server (:3000) are already running — `scripts/e2e-ui.sh` starts them.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    locale: "zh-CN",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
