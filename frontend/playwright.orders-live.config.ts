import { defineConfig, devices } from '@playwright/test';
import liveConfig from './playwright.live.config';

export default defineConfig({
  ...liveConfig,
  testMatch: 'orders.spec.ts',
  reporter: [
    ['list'],
    ['json', { outputFile: '../tests/results/orders-results.json' }],
  ],
  outputDir: 'test-results/live-orders',
  projects: [
    {
      name: 'desktop-live',
      use: {
        ...devices['Desktop Chrome'],
        channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
      },
    },
    {
      name: 'mobile-live',
      use: {
        ...devices['iPhone 13'],
        defaultBrowserType: 'chromium',
        channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
      },
    },
  ],
});
