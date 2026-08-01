import path from "node:path";
import { defineConfig } from "@playwright/test";

import { E2E_PATHS } from "./paths";
import { E2E_TIMEOUTS } from "./timeouts";

const e2ePort = process.env.PLAYWRIGHT_PORT || "5174";
const e2eMode = process.env.PLAYWRIGHT_MODE === "live" ? "live" : "mock";
const e2eBaseURL =
  process.env.PLAYWRIGHT_BASE_URL ||
  process.env.WEB_URL ||
  (e2eMode === "live" ? "http://127.0.0.1:5173" : `http://127.0.0.1:${e2ePort}`);

export default defineConfig({
  testDir: E2E_PATHS.specs,
  outputDir: path.join(E2E_PATHS.testResults, e2eMode),
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: path.join(E2E_PATHS.report, e2eMode), open: "never" }],
  ],
  expect: {
    timeout: E2E_TIMEOUTS.expect,
  },
  use: {
    baseURL: e2eBaseURL,
    actionTimeout: E2E_TIMEOUTS.action,
    navigationTimeout: E2E_TIMEOUTS.navigation,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer:
    e2eMode === "live"
      ? undefined
      : {
          command: `pnpm dev --host 127.0.0.1 --port ${e2ePort}`,
          url: e2eBaseURL,
          reuseExistingServer: process.env.PLAYWRIGHT_REUSE_EXISTING_SERVER === "1",
          timeout: E2E_TIMEOUTS.webServer,
          env: {
            VITE_AUTH_ENABLED: "true",
          },
        },
  globalSetup: path.join(E2E_PATHS.root, "global-setup.ts"),
  projects: [
    {
      name: "mock",
      grep: /@mock/,
      timeout: E2E_TIMEOUTS.test.mock,
      use: {},
    },
    {
      name: "live",
      grep: /@live/,
      use: {
        storageState: E2E_PATHS.authState,
      },
      timeout: E2E_TIMEOUTS.test.live,
      retries: process.env.CI ? 1 : 0,
    },
  ],
});
