import { defineConfig } from '@playwright/test';
import loginConfig from './playwright.live.config';

export default defineConfig({
  ...loginConfig,
  testMatch: 'admin.spec.ts',
  reporter: [
    ['list'],
    ['json', { outputFile: '../tests/results/admin-results.json' }],
  ],
  outputDir: 'test-results/live-admin',
});
