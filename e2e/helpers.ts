/**
 * CloseLoop CRM — shared e2e test helpers
 *
 * Exports the extended `test` fixture (with automatic JS-error guard),
 * credential constants, and auth/navigation helpers used by all spec files.
 */

import { test as base, expect, type Page } from '@playwright/test';

// ── Constants ─────────────────────────────────────────────────────────────────
export const TEST_USER = process.env.TEST_USER ?? 'admin@closeloop.com';
export const TEST_PASS = process.env.TEST_PASS ?? 'admin123';

// ── Auto-fixture: collect JS errors and fail the test if any occurred ──────────
export const test = base.extend<{ _jsGuard: void }>({
  _jsGuard: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on('pageerror', (err) => errors.push(`Uncaught: ${err.message}`));
      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          // Chromium emits a console.error for every non-2xx fetch response (e.g. 401
          // on intentional failed login).  These are browser-generated network messages,
          // not JavaScript errors in our application code, so we skip them here.
          if (msg.text().startsWith('Failed to load resource:')) return;
          errors.push(`console.error: ${msg.text()}`);
        }
      });
      await use();
      for (const e of errors) {
        expect.soft(e, 'Browser-side JavaScript error').toBeFalsy();
      }
    },
    { auto: true },
  ],
});

// ── Helpers ───────────────────────────────────────────────────────────────────

export async function login(page: Page, email = TEST_USER, pass = TEST_PASS) {
  await page.goto('/login.html');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(pass);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

/** Login and wait until the dashboard nav tabs are visible. */
export async function loginAndWait(page: Page) {
  await login(page);
  await expect(page.getByRole('button', { name: 'Pipeline' })).toBeVisible({ timeout: 15_000 });
}

/**
 * Reload the page and wait for the dashboard to re-hydrate from localStorage.
 * Use this after creating data via API so the React state picks up the new rows.
 */
export async function reloadDashboard(page: Page) {
  await page.reload();
  await expect(page.getByRole('button', { name: 'Pipeline' })).toBeVisible({ timeout: 15_000 });
}

/** Read the Bearer token from the page's localStorage. */
export async function bearerToken(page: Page): Promise<string> {
  const t = await page.evaluate(() => localStorage.getItem('access_token'));
  if (!t) throw new Error('access_token not found in localStorage');
  return t;
}

/** Auth headers shorthand. */
export function auth(tok: string) {
  return { Authorization: `Bearer ${tok}` };
}
