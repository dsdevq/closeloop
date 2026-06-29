/**
 * CloseLoop CRM — Today e2e tests
 *
 * Covers: today tab navigation, reminder dismiss flow.
 *
 * Run:  npx playwright test --reporter=list
 * Env:  TEST_USER / TEST_PASS (defaults: admin@closeloop.com / admin123)
 */

import { expect } from '@playwright/test';
import { test, loginAndWait, reloadDashboard, bearerToken, auth } from './helpers';

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
