import { defineConfig, devices } from '@playwright/test'

// Runs against an already-running stack (docker compose), default the `web` service.
export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  reporter: [['list']],
  // One worker: specs share the isolated e2e database and reset it between tests.
  workers: 1,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
