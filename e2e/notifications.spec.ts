/**
 * CloseLoop CRM — Notification centre e2e tests
 *
 * Surface: HubSpot-style bell icon + dropdown panel (notifications-engine.md §2.2).
 * Backend: GET /notifications, GET /notifications/unread-count,
 *           POST /notifications/{id}/read, POST /notifications/read-all.
 *
 * Reference CRM rationale (notifications-engine.md §3):
 *   Borrowed: pull-model badge polling (HubSpot/Pipedrive), flat list (all five),
 *             read_at timestamp not boolean (HubSpot/Attio), kind icon dispatch (Pipedrive).
 *   Rejected: Chatter/feed page-level view (over-engineered), Zoho day-grouping (FE concern).
 *
 * Run:  npx playwright test --reporter=list
 * Env:  TEST_USER / TEST_PASS (defaults: admin@closeloop.com / admin123)
 */

import { test as base, expect, type Page, type APIRequestContext } from '@playwright/test';

// ── Auto-fixture: collect JS errors and fail the test if any occurred ──────────
const test = base.extend<{ _jsGuard: void }>({
  _jsGuard: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on('pageerror', (err) => errors.push(`Uncaught: ${err.message}`));
      page.on('console', (msg) => {
        if (msg.type() === 'error') {
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

async function loginAndWait(page: Page) {
  await login(page);
  await expect(page.getByRole('button', { name: 'Pipeline' })).toBeVisible({ timeout: 15_000 });
}

async function reloadDashboard(page: Page) {
  await page.reload();
  await expect(page.getByRole('button', { name: 'Pipeline' })).toBeVisible({ timeout: 15_000 });
}

async function bearerToken(page: Page): Promise<string> {
  const t = await page.evaluate(() => localStorage.getItem('access_token'));
  if (!t) throw new Error('access_token not found in localStorage');
  return t;
}

function auth(tok: string) {
  return { Authorization: `Bearer ${tok}` };
}

/**
 * Register a rep user as admin and return the rep's login token.
 * Cleans up via the returned teardown function (deletes created activity, not the user
 * since there is no DELETE /users endpoint — users created here are test-only and
 * the in-memory SQLite DB is wiped between test runs).
 */
async function registerRepAndGetToken(
  request: APIRequestContext,
  adminTok: string,
  email: string,
  password: string,
): Promise<string> {
  const regRes = await request.post('/auth/register', {
    data: { email, password, full_name: 'Rep User', role: 'rep' },
    headers: auth(adminTok),
  });
  // 422 means already registered — that's fine, just login
  if (!regRes.ok() && regRes.status() !== 422) {
    throw new Error(`Failed to register rep user: ${await regRes.text()}`);
  }

  const loginRes = await request.post('/auth/login', {
    data: { email, password },
  });
  expect(loginRes.ok()).toBeTruthy();
  const data = await loginRes.json() as { access_token: string };
  return data.access_token;
}

// ── Navigation / shell tests ──────────────────────────────────────────────────

test.describe('Notification bell — shell', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndWait(page);
  });

  test('bell icon is visible in the header', async ({ page }) => {
    await expect(page.getByTestId('notification-bell')).toBeVisible();
  });

  test('no badge when there are no notifications', async ({ page }) => {
    // Badge only renders when unread_count > 0
    await expect(page.getByTestId('notification-badge')).not.toBeVisible();
  });

  test('panel opens when bell is clicked', async ({ page }) => {
    await page.getByTestId('notification-bell').click();
    await expect(page.getByTestId('notification-panel')).toBeVisible({ timeout: 5_000 });
  });

  test('panel shows empty-state message when no notifications', async ({ page }) => {
    await page.getByTestId('notification-bell').click();
    await expect(page.getByTestId('notification-empty')).toBeVisible({ timeout: 5_000 });
  });

  test('panel closes when Escape is pressed', async ({ page }) => {
    await page.getByTestId('notification-bell').click();
    await expect(page.getByTestId('notification-panel')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('notification-panel')).not.toBeVisible({ timeout: 3_000 });
  });

  test('panel closes when clicking outside', async ({ page }) => {
    await page.getByTestId('notification-bell').click();
    await expect(page.getByTestId('notification-panel')).toBeVisible();
    // Click the page heading — outside the notification widget
    await page.locator('header').click({ position: { x: 10, y: 30 } });
    await expect(page.getByTestId('notification-panel')).not.toBeVisible({ timeout: 3_000 });
  });
});

// ── Notification content + interactions ───────────────────────────────────────

test.describe('Notification content and mark-as-read', () => {
  /**
   * Strategy: create a real notification via trigger wiring.
   *
   * Admin's email is admin@closeloop.com → mention token is "admin".
   * A rep user creates a note activity with body "@admin" → MentionEvent
   * fires for admin (non-self-mention).  Self-mention suppression (actor==recipient)
   * is the reason we need a second actor rather than admin self-mentioning.
   *
   * Reference: notifications-engine.md §3 (MentionEvent kind, Zoho @mention pattern).
   */

  const REP_EMAIL = 'e2e-rep-notifications@example.com';
  const REP_PASS = 'notif-rep-pass123';

  test('unread badge appears and panel shows the notification', async ({ page, request }) => {
    await loginAndWait(page);
    const adminTok = await bearerToken(page);

    // Register the rep (idempotent — 422 means already exists)
    const repTok = await registerRepAndGetToken(request, adminTok, REP_EMAIL, REP_PASS);

    // Rep creates a note mentioning @admin — triggers MentionEvent for admin
    const actRes = await request.post('/activities', {
      data: { title: 'NC Badge Test Note', type: 'note', body: '@admin check this out' },
      headers: auth(repTok),
    });
    expect(actRes.ok()).toBeTruthy();
    const activity = await actRes.json() as { id: number };

    try {
      // Reload so the polling cycle re-runs from mount
      await reloadDashboard(page);

      // Wait for the unread badge to appear — the page polls /notifications/unread-count
      await expect(page.getByTestId('notification-badge')).toBeVisible({ timeout: 10_000 });

      // Open the panel — it fetches GET /notifications
      const notifResp = page.waitForResponse(
        (r) => r.url().includes('/notifications') && !r.url().includes('unread-count'),
        { timeout: 8_000 },
      );
      await page.getByTestId('notification-bell').click();
      expect((await notifResp).ok()).toBeTruthy();

      // Panel visible and not showing the empty state
      await expect(page.getByTestId('notification-panel')).toBeVisible();
      await expect(page.getByTestId('notification-empty')).not.toBeVisible();

      // At least one notification row exists
      const rows = page.locator('[data-testid="notification-panel"] button[aria-label^="Mark as read"]');
      await expect(rows.first()).toBeVisible({ timeout: 5_000 });
    } finally {
      await request.delete(`/activities/${activity.id}`, { headers: auth(adminTok) });
    }
  });

  test('clicking an unread notification marks it read and removes badge dot', async ({ page, request }) => {
    await loginAndWait(page);
    const adminTok = await bearerToken(page);

    const repTok = await registerRepAndGetToken(request, adminTok, REP_EMAIL, REP_PASS);

    const actRes = await request.post('/activities', {
      data: { title: 'NC MarkRead Test Note', type: 'note', body: '@admin please review' },
      headers: auth(repTok),
    });
    expect(actRes.ok()).toBeTruthy();
    const activity = await actRes.json() as { id: number };

    try {
      await reloadDashboard(page);

      // Wait for badge
      await expect(page.getByTestId('notification-badge')).toBeVisible({ timeout: 10_000 });

      // Open panel
      await page.getByTestId('notification-bell').click();
      await expect(page.getByTestId('notification-panel')).toBeVisible();

      // Find the unread row and click it — triggers POST /notifications/{id}/read
      const unreadRow = page
        .locator('[data-testid="notification-panel"] button[aria-label^="Mark as read"]')
        .first();
      await expect(unreadRow).toBeVisible({ timeout: 5_000 });

      const markReadResp = page.waitForResponse(
        (r) => r.url().includes('/notifications/') && r.url().includes('/read'),
        { timeout: 8_000 },
      );
      await unreadRow.click();
      expect((await markReadResp).ok()).toBeTruthy();

      // After marking read, the badge should be gone (all notifications read)
      await expect(page.getByTestId('notification-badge')).not.toBeVisible({ timeout: 5_000 });
    } finally {
      await request.delete(`/activities/${activity.id}`, { headers: auth(adminTok) });
    }
  });

  test('mark-all-read button hits POST /notifications/read-all and clears badge', async ({
    page,
    request,
  }) => {
    await loginAndWait(page);
    const adminTok = await bearerToken(page);

    const repTok = await registerRepAndGetToken(request, adminTok, REP_EMAIL, REP_PASS);

    const actRes = await request.post('/activities', {
      data: { title: 'NC MarkAll Test Note', type: 'note', body: '@admin fyi' },
      headers: auth(repTok),
    });
    expect(actRes.ok()).toBeTruthy();
    const activity = await actRes.json() as { id: number };

    try {
      await reloadDashboard(page);
      await expect(page.getByTestId('notification-badge')).toBeVisible({ timeout: 10_000 });

      await page.getByTestId('notification-bell').click();
      await expect(page.getByTestId('notification-panel')).toBeVisible();
      await expect(page.getByTestId('mark-all-read-btn')).toBeVisible({ timeout: 5_000 });

      // Click mark-all-read — should hit POST /notifications/read-all (204)
      const markAllResp = page.waitForResponse(
        (r) => r.url().endsWith('/notifications/read-all'),
        { timeout: 8_000 },
      );
      await page.getByTestId('mark-all-read-btn').click();
      const resp = await markAllResp;
      expect(resp.ok()).toBeTruthy();
      expect(resp.status()).toBe(204);

      // Badge must disappear
      await expect(page.getByTestId('notification-badge')).not.toBeVisible({ timeout: 5_000 });
      // Mark-all-read button disappears when no unread remain
      await expect(page.getByTestId('mark-all-read-btn')).not.toBeVisible({ timeout: 3_000 });
    } finally {
      await request.delete(`/activities/${activity.id}`, { headers: auth(adminTok) });
    }
  });
});

// ── API contract: unread-count endpoint is polled ─────────────────────────────

test.describe('Backend wiring', () => {
  test('page polls GET /notifications/unread-count on load', async ({ page }) => {
    const countResp = page.waitForResponse(
      (r) => r.url().includes('/notifications/unread-count') && r.status() === 200,
      { timeout: 10_000 },
    );
    await loginAndWait(page);
    expect((await countResp).ok()).toBeTruthy();
  });
});
