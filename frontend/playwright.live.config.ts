import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e-live',
  testMatch: 'login.spec.ts',
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: '../.qa/login-results.json' }]],
  outputDir: 'test-results/live-login',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5181',
    // A trace can contain Authorization headers; do not retain real JWTs.
    trace: 'off',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'desktop-live',
      use: {
        ...devices['Desktop Chrome'],
        channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
      },
    },
  ],
});
