import { defineConfig, devices } from '@playwright/test';
import path from 'path';

// On some Linux environments libXfixes.so.3 is not installed system-wide.
// We stash a user-space copy in ~/lib (extracted from the .deb without root)
// and make it visible to Chromium via LD_LIBRARY_PATH.
const userLib = path.join(process.env.HOME ?? '/home/agent', 'lib');
process.env.LD_LIBRARY_PATH = process.env.LD_LIBRARY_PATH
  ? `${userLib}:${process.env.LD_LIBRARY_PATH}`
  : userLib;

// Port 8000 may be occupied by a harness-managed stub in some CI environments.
// Use 8088 for the e2e server to avoid the conflict.
const E2E_PORT = Number(process.env.E2E_PORT ?? 8088);

export default defineConfig({
  testDir: './e2e',
  reporter: [['list'], ['html', { open: 'never' }]],
  retries: 0,
  // Single worker so tests within the file run serially and don't race on shared DB
  workers: 1,
  use: {
    baseURL: `http://localhost:${E2E_PORT}`,
    headless: true,
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // Auto-start the FastAPI server on E2E_PORT; reuse if already running.
  // stdout/stderr are not piped: piping on ARM64 fills the OS pipe buffer
  // after ~10 tests and stalls uvicorn, causing subsequent tests to time out.
  webServer: {
    command: `uvicorn app.main:app --host 127.0.0.1 --port ${E2E_PORT} --log-level warning`,
    url: `http://localhost:${E2E_PORT}/health`,
    reuseExistingServer: true,
    timeout: 30_000,
    stdout: 'ignore',
    stderr: 'ignore',
  },
});
