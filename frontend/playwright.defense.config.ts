import { defineConfig } from '@playwright/test';
import live from './playwright.live.config';
export default defineConfig({
  ...live,
  testMatch: 'defense.spec.ts',
  reporter: 'list',
  outputDir: 'test-results/defense',
  use: {
    ...live.use,
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5183',
  },
});
