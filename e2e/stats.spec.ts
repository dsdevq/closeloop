/**
 * CloseLoop CRM — Stats e2e tests
 *
 * Covers: stats tab navigation.
 *
 * Run:  npx playwright test --reporter=list
 * Env:  TEST_USER / TEST_PASS (defaults: admin@closeloop.com / admin123)
 */

import { expect } from '@playwright/test';
import { test, loginAndWait } from './helpers';

// ── Navigation ────────────────────────────────────────────────────────────────

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndWait(page);
  });

  test('"Stats" tab is clickable and renders non-blank content', async ({ page }) => {
    await page.getByRole('button', { name: 'Stats' }).click();
    const main = page.locator('main');
    await expect(main).toBeVisible();
    const text = await main.textContent();
    expect((text ?? '').trim().length).toBeGreaterThan(0);
  });
});
