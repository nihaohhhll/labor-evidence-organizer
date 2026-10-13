import { defineConfig } from "vitest/config";

// Unit tests live under src/; e2e/ holds Playwright specs, which must not be
// collected by vitest (`npm test` used to fail on e2e/phase9c-ui.spec.ts).
export default defineConfig({
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
