import { defineConfig } from '@playwright/test';
import liveConfig from './playwright.live.config';

export default defineConfig({
  ...liveConfig,
  testMatch: 'cutoff.spec.ts',
  reporter: [
    ['list'],
    ['json', { outputFile: '../tests/results/cutoff-results.json' }],
  ],
  outputDir: 'test-results/live-cutoff',
});
