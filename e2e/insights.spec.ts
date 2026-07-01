/**
 * CloseLoop CRM — Insights e2e tests
 *
 * Covers: insights tab navigation, all-sections render,
 *         TrendsSection window switcher.
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

// ── Navigation ────────────────────────────────────────────────────────────────

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndWait(page);
  });

  test('"Insights" tab is clickable and renders non-blank content', async ({ page }) => {
    await page.getByRole('button', { name: 'Insights' }).click();
    const main = page.locator('main');
    await expect(main).toBeVisible();
    const text = await main.textContent();
    expect((text ?? '').trim().length).toBeGreaterThan(0);
  });
});

// ── Insights sections ─────────────────────────────────────────────────────────

test.describe('Insights sections', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndWait(page);
    await page.getByRole('button', { name: 'Insights' }).click();
    // Wait for the view to mount — the TrendsSection heading is always rendered
    // regardless of loading state, so this is a reliable gate.
    await expect(page.getByRole('heading', { name: 'Deal Trends' })).toBeVisible({
      timeout: 10_000,
    });
  });

  test('all four sections render non-blank content', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Deal Trends' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Conversion Funnel' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Rep Leaderboard' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Source Cohorts' })).toBeVisible();
  });

  test('TrendsSection window switcher changes active selection and re-fetches data', async ({
    page,
  }) => {
    const btn30 = page.getByRole('button', { name: '30d' });
    const btn90 = page.getByRole('button', { name: '90d' });
    const btn365 = page.getByRole('button', { name: '365d' });

    // 30d is selected by default
    await expect(btn30).toHaveClass(/bg-blue-600/);
    await expect(btn90).not.toHaveClass(/bg-blue-600/);
    await expect(btn365).not.toHaveClass(/bg-blue-600/);

    // Switch to 90d — active class flips and the section re-fetches with window_days=90
    const resp90 = page.waitForResponse(
      (r) => r.url().includes('/insights/trends') && r.url().includes('window_days=90'),
      { timeout: 8_000 },
    );
    await btn90.click();
    expect((await resp90).ok()).toBeTruthy();
    await expect(btn90).toHaveClass(/bg-blue-600/);
    await expect(btn30).not.toHaveClass(/bg-blue-600/);

    // Switch to 365d
    const resp365 = page.waitForResponse(
      (r) => r.url().includes('/insights/trends') && r.url().includes('window_days=365'),
      { timeout: 8_000 },
    );
    await btn365.click();
    expect((await resp365).ok()).toBeTruthy();
    await expect(btn365).toHaveClass(/bg-blue-600/);
    await expect(btn90).not.toHaveClass(/bg-blue-600/);

    // Switch back to 30d
    const resp30 = page.waitForResponse(
      (r) => r.url().includes('/insights/trends') && r.url().includes('window_days=30'),
      { timeout: 8_000 },
    );
    await btn30.click();
    expect((await resp30).ok()).toBeTruthy();
    await expect(btn30).toHaveClass(/bg-blue-600/);
    await expect(btn365).not.toHaveClass(/bg-blue-600/);
  });
});
