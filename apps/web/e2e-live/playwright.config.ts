import { defineConfig } from '@playwright/test'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

export default defineConfig({
  testDir: './tests',
  timeout: 60000,
  retries: 1,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report-live' }]],
  use: {
    baseURL: process.env.WEB_URL || 'http://localhost:5173',
    storageState: join(__dirname, 'storageState.json'),
    headless: true,
  },
  globalSetup: join(__dirname, 'global-setup.ts'),
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
})
