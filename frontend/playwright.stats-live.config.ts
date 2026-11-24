import { defineConfig } from '@playwright/test';
import ordersConfig from './playwright.orders-live.config';

export default defineConfig({
  ...ordersConfig,
  testMatch: 'stats.spec.ts',
  reporter: [
    ['list'],
    ['json', { outputFile: '../tests/results/stats-results.json' }],
  ],
  outputDir: 'test-results/live-stats',
});
