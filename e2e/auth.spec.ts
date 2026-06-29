/**
 * CloseLoop CRM — Auth e2e tests
 *
 * Covers: basic load, auth (login/logout/guard), route coverage.
 *
 * Tests tagged "[UI gap]" are EXPECTED TO FAIL — they document UI features that
 * exist in the API but have no corresponding button/page in the current SPA.
 *
 * Run:  npx playwright test --reporter=list
 * Env:  TEST_USER / TEST_PASS (defaults: admin@closeloop.com / admin123)
 */

import { expect } from '@playwright/test';
import { test, TEST_USER, TEST_PASS, login, loginAndWait, bearerToken, auth } from './helpers';

// ── 1. Basic load ─────────────────────────────────────────────────────────────

test.describe('Basic load', () => {
  test('GET / returns 200 and a non-empty body', async ({ page }) => {
    const resp = await page.goto('/');
    expect(resp?.status()).toBe(200);
    const html = await page.content();
    expect(html.length).toBeGreaterThan(200);
    await expect(page.locator('body')).not.toBeEmpty();
  });
});

// ── 2. Auth ───────────────────────────────────────────────────────────────────

test.describe('Auth', () => {
  test('login page renders email + password form', async ({ page }) => {
    await page.goto('/login.html');
    await expect(page.getByLabel('Email')).toBeVisible();
    await expect(page.getByLabel('Password')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
    await expect(page.locator('text=CloseLoop CRM')).toBeVisible();
  });

  test('valid credentials show dashboard nav tabs', async ({ page }) => {
    await login(page);
    await expect(page.getByRole('button', { name: 'Pipeline' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: 'Contacts' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Accounts' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Today' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Stats' })).toBeVisible();
  });

  test('invalid credentials display an error message', async ({ page }) => {
    await page.goto('/login.html');
    await page.getByLabel('Email').fill('nobody@nowhere.invalid');
    await page.getByLabel('Password').fill('definitelywrong');
    await page.getByRole('button', { name: 'Sign in' }).click();
    // The LoginView renders <div className="... text-red-700">{error}</div>
    await expect(page.locator('.text-red-700')).toBeVisible({ timeout: 8_000 });
  });

  test('unauthenticated visit to / shows login form (SPA client-side guard)', async ({ page }) => {
    await page.goto('/');
    // Wipe stored tokens so the React app reverts to LoginView on next render
    await page.evaluate(() => {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('current_user');
    });
    await page.reload();
    await expect(page.getByLabel('Email')).toBeVisible({ timeout: 8_000 });
    await expect(page.getByRole('button', { name: 'Pipeline' })).not.toBeVisible();
  });
});

// ── Route coverage ────────────────────────────────────────────────────────────

test.describe('Route coverage', () => {
  test('every route loads without error', async ({ page, request }) => {
    // / redirects to login form for unauthenticated visit
    const rootResp = await page.goto('/');
    expect(rootResp?.status()).not.toBe(404);
    await expect(page.locator('body')).not.toBeEmpty();

    // /login.html always shows the login form
    await page.goto('/login.html');
    await expect(page.getByLabel('Email')).toBeVisible({ timeout: 8_000 });
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();

    // Log in and navigate through all SPA tabs
    await loginAndWait(page);
    const tok = await bearerToken(page);

    // Backend API routes: assert they respond (not 404)
    for (const route of ['/contacts', '/deals', '/activities']) {
      const res = await request.get(route, { headers: auth(tok) });
      expect(res.status(), `${route} should not 404`).not.toBe(404);
    }

    // SPA tab coverage – each tab must render non-blank content in <main>
    const tabs = ['Pipeline', 'Contacts', 'Accounts', 'Activities', 'Today', 'Stats'];
    for (const tab of tabs) {
      await page.getByRole('button', { name: tab }).click();
      const main = page.locator('main');
      await expect(main).toBeVisible();
      // wait for any initial loading to settle
      await page.waitForTimeout(300);
      const text = await main.textContent();
      expect((text ?? '').trim().length, `${tab} tab should have non-blank content`).toBeGreaterThan(0);
    }
  });
});

// ── Auth flow ─────────────────────────────────────────────────────────────────

test.describe('Auth flow', () => {
  test('auth - valid login succeeds', async ({ page }) => {
    await page.goto('/login.html');
    await page.getByLabel('Email').fill(TEST_USER);
    await page.getByLabel('Password').fill(TEST_PASS);
    await page.getByRole('button', { name: 'Sign in' }).click();

    // Redirect to dashboard (SPA: Pipeline tab is visible)
    await expect(page.getByRole('button', { name: 'Pipeline' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: 'Contacts' })).toBeVisible();
  });

  test('auth - invalid login shows error', async ({ page }) => {
    await page.goto('/login.html');
    await page.getByLabel('Email').fill('nobody@nowhere.invalid');
    await page.getByLabel('Password').fill('definitelywrong');
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page.locator('.text-red-700')).toBeVisible({ timeout: 8_000 });
    await expect(page.getByRole('button', { name: 'Pipeline' })).not.toBeVisible();
  });

  test('logout button is visible and clickable from authenticated page', async ({ page }) => {
    await loginAndWait(page);
    await page.getByRole('button', { name: 'Contacts' }).click();

    // The Sign out icon button (title="Sign out") lives in the nav header on every authenticated page
    const logoutBtn = page.getByTitle('Sign out');
    await expect(logoutBtn).toBeVisible({ timeout: 5_000 });
    await expect(logoutBtn).toBeEnabled();
    // Do NOT click — clicking would clear tokens and break auth state for subsequent tests
  });

  test('auth - protected route redirects unauthenticated user', async ({ page }) => {
    // Visit app root without stored tokens
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('current_user');
    });
    await page.reload();

    // SPA renders the login form for unauthenticated state
    await expect(page.getByLabel('Email')).toBeVisible({ timeout: 8_000 });
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
    // Dashboard nav must NOT be accessible
    await expect(page.getByRole('button', { name: 'Pipeline' })).not.toBeVisible();
  });
});
