import { defineConfig } from "@playwright/test";

const e2ePort = process.env.PLAYWRIGHT_PORT || "5174";
const e2eBaseURL = process.env.PLAYWRIGHT_BASE_URL || `http://127.0.0.1:${e2ePort}`;

export default defineConfig({
  testDir: ".",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [["list"], ["html", { outputFolder: ".playwright-report" }]],
  use: {
    baseURL: e2eBaseURL,
    trace: "on-first-retry",
  },
  webServer: {
    command: `pnpm dev --host 127.0.0.1 --port ${e2ePort}`,
    url: e2eBaseURL,
    reuseExistingServer: process.env.PLAYWRIGHT_REUSE_EXISTING_SERVER === "1",
    env: {
      VITE_AUTH_ENABLED: "true",
    },
  },
  globalSetup: "./global-setup.ts",
  projects: [
    {
      name: "mock",
      grep: /@mock/,
      use: {},
    },
    {
      name: "live",
      grep: /@live/,
      use: {
        storageState: ".auth/state.json",
      },
      timeout: 60_000,
      retries: process.env.CI ? 1 : 0,
    },
  ],
});
