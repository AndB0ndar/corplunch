import { defineConfig } from '@playwright/test';
import loginConfig from './playwright.live.config';

export default defineConfig({
  ...loginConfig,
  testMatch: 'plans.spec.ts',
  reporter: [
    ['list'],
    ['json', { outputFile: '../tests/results/plans-results.json' }],
  ],
  outputDir: 'test-results/live-plans',
});
