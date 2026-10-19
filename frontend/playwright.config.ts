// پیکربندی Playwright E2E (فاز ۴) — سرور بک‌اند با build فرانت‌اند روی 8000
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: 'http://127.0.0.1:8000',
    locale: 'fa-IR',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
  webServer: {
    command: 'bash ../scripts/e2e-server.sh',
    url: 'http://127.0.0.1:8000/api/v1/health',
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    cwd: '.',
  },
});
