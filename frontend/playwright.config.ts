import { defineConfig } from '@playwright/test'
import process from 'node:process'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

export default defineConfig({
  testDir: './tests/browser',
  workers: 1,
  // A per-run temp directory avoids OneDrive locks on prior trace artifacts.
  outputDir: join(tmpdir(), `coolroof-browser-${process.pid}`),
  timeout: 90_000,
  globalSetup: './tests/browser/prepare-round.ts',
  globalTeardown: './tests/browser/prepare-round.ts',
  use: {
    baseURL: 'http://localhost:5173',
    channel: process.env.PLAYWRIGHT_CHANNEL ?? 'chrome',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
})
