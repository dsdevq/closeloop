/**
 * CloseLoop CRM — Today e2e tests
 *
 * Covers: today tab navigation, reminder dismiss flow.
 *
 * Run:  npx playwright test --reporter=list
 * Env:  TEST_USER / TEST_PASS (defaults: admin@closeloop.com / admin123)
 */

import { test as base, expect, type Page } from '@playwright/test';

// ── Auto-fixture: collect JS errors and fail the test if any occurred ──────────
const test = base.extend<{ _jsGuard: void }>({
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

// ── Constants ─────────────────────────────────────────────────────────────────
const TEST_USER = process.env.TEST_USER ?? 'admin@closeloop.com';
const TEST_PASS = process.env.TEST_PASS ?? 'admin123';

// ── Helpers ───────────────────────────────────────────────────────────────────

async function login(page: Page, email = TEST_USER, pass = TEST_PASS) {
  await page.goto('/login.html');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(pass);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

/** Login and wait until the dashboard nav tabs are visible. */
async function loginAndWait(page: Page) {
  await login(page);
  await expect(page.getByRole('button', { name: 'Pipeline' })).toBeVisible({ timeout: 15_000 });
}

/**
 * Reload the page and wait for the dashboard to re-hydrate from localStorage.
 * Use this after creating data via API so the React state picks up the new rows.
 */
async function reloadDashboard(page: Page) {
  await page.reload();
  await expect(page.getByRole('button', { name: 'Pipeline' })).toBeVisible({ timeout: 15_000 });
}

/** Read the Bearer token from the page's localStorage. */
async function bearerToken(page: Page): Promise<string> {
  const t = await page.evaluate(() => localStorage.getItem('access_token'));
  if (!t) throw new Error('access_token not found in localStorage');
  return t;
}

/** Auth headers shorthand. */
function auth(tok: string) {
  return { Authorization: `Bearer ${tok}` };
}

// ── Navigation ────────────────────────────────────────────────────────────────

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndWait(page);
  });

  test('"Today" tab is clickable and renders non-blank content', async ({ page }) => {
    await page.getByRole('button', { name: 'Today' }).click();
    const main = page.locator('main');
    await expect(main).toBeVisible();
    const text = await main.textContent();
    expect((text ?? '').trim().length).toBeGreaterThan(0);
  });
});

// ── Extended interactive controls (today) ─────────────────────────────────────

test.describe('Extended interactive controls', () => {
  test('today - dismiss reminder removes it from list', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    // Create an activity to attach the reminder to
    const activityRes = await request.post('/activities', {
      data: { title: 'FC Today Dismiss Activity', type: 'call' },
      headers: auth(tok),
    });
    expect(activityRes.ok()).toBeTruthy();
    const activity = await activityRes.json();

    // A past remind_at guarantees the reminder appears in GET /reminders/today
    const reminderRes = await request.post('/reminders', {
      data: { activity_id: activity.id, remind_at: '2020-01-01T00:00:00+00:00' },
      headers: auth(tok),
    });
    expect(reminderRes.ok()).toBeTruthy();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Today' }).click();

      // Reminder row appears with the activity title
      await expect(page.getByText('FC Today Dismiss Activity')).toBeVisible({ timeout: 8_000 });

      // Scope to the specific reminder row to avoid collisions with other reminders
      const reminderRow = page.locator('.panel').filter({ hasText: 'FC Today Dismiss Activity' });

      const dismissPromise = page.waitForResponse(
        (resp) => resp.url().includes('/reminders/') && resp.url().includes('/dismiss'),
        { timeout: 8_000 },
      );
      await reminderRow.getByRole('button', { name: 'Dismiss' }).click();
      const dismissResp = await dismissPromise;
      expect(dismissResp.ok()).toBeTruthy();

      // Reminder is removed from the Today list
      await expect(page.getByText('FC Today Dismiss Activity')).not.toBeVisible({ timeout: 5_000 });
    } finally {
      // Deleting the activity cascades to delete the reminder
      await request.delete(`/activities/${activity.id}`, { headers: auth(tok) });
    }
  });
});
