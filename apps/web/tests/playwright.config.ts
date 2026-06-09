import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: '.',
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [['list'], ['html', { outputFolder: '.playwright-report' }]],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'pnpm dev --host 127.0.0.1 --port 5173',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: !process.env.CI,
    env: {
      VITE_AUTH_ENABLED: 'true',
    },
  },
  globalSetup: './global-setup.ts',
  projects: [
    {
      name: 'mock',
      grep: /@mock/,
      use: {},
    },
    {
      name: 'live',
      grep: /@live/,
      use: {
        storageState: '.auth/state.json',
      },
      timeout: 60_000,
      retries: process.env.CI ? 1 : 0,
    },
  ],
})
