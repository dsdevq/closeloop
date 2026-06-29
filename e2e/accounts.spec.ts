/**
 * CloseLoop CRM — Accounts e2e tests
 *
 * Covers: accounts tab navigation, Accounts CRUD (smoke + full-coverage).
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

  test('"Accounts" tab is clickable and renders non-blank content', async ({ page }) => {
    await page.getByRole('button', { name: 'Accounts' }).click();
    const main = page.locator('main');
    await expect(main).toBeVisible();
    const text = await main.textContent();
    expect((text ?? '').trim().length).toBeGreaterThan(0);
  });
});

// ── Accounts CRUD ─────────────────────────────────────────────────────────────

test.describe('Accounts CRUD', () => {
  test('create account via New Account modal — appears in accounts list', async ({ page, request }) => {
    await loginAndWait(page);
    await page.getByRole('button', { name: 'Accounts' }).click();
    await page.getByRole('button', { name: 'New Account' }).click();

    await expect(page.getByRole('heading', { name: 'New Account' })).toBeVisible();
    await page.getByLabel('Name').fill('Smoke Account Corp');
    await page.getByLabel('Domain').fill('smoke.example.com');
    await page.getByLabel('Industry').fill('Technology');
    await page.getByRole('button', { name: 'Create' }).click();

    await expect(page.getByRole('cell', { name: 'Smoke Account Corp' })).toBeVisible({ timeout: 8_000 });

    // Cleanup
    const tok = await bearerToken(page);
    const list: { id: number; name: string }[] = await (
      await request.get('/accounts', { headers: auth(tok) })
    ).json();
    const acc = list.find((a) => a.name === 'Smoke Account Corp');
    if (acc) await request.delete(`/accounts/${acc.id}`, { headers: auth(tok) });
  });

  test('open account detail view — shows domain and linked contacts section', async ({
    page,
    request,
  }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const createRes = await request.post('/accounts', {
      data: { name: 'Detail Account', domain: 'detail.example.com', industry: 'Finance' },
      headers: auth(tok),
    });
    const account = await createRes.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Accounts' }).click();
      await expect(page.getByRole('cell', { name: 'Detail Account' })).toBeVisible({ timeout: 8_000 });

      // Click the account name button in the table row to open the detail view
      await page.getByRole('button', { name: 'Detail Account' }).first().click();

      await expect(page.getByRole('heading', { name: 'Detail Account' })).toBeVisible({ timeout: 5_000 });
      await expect(page.getByText('Domain')).toBeVisible();
      await expect(page.getByText('detail.example.com')).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Linked Contacts' })).toBeVisible();
    } finally {
      await request.delete(`/accounts/${account.id}`, { headers: auth(tok) });
    }
  });

  test('edit account — stub Edit button is visible in account detail view', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const createRes = await request.post('/accounts', {
      data: { name: 'Edit Stub Account' },
      headers: auth(tok),
    });
    const account = await createRes.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Accounts' }).click();
      await page.getByRole('button', { name: 'Edit Stub Account' }).first().click();
      await expect(page.getByRole('heading', { name: 'Edit Stub Account' })).toBeVisible({ timeout: 5_000 });

      // Stub Edit button is present in the DOM (disabled — full form is a follow-up goal)
      await expect(page.getByRole('button', { name: /^edit$/i })).toBeVisible({ timeout: 3_000 });
    } finally {
      await request.delete(`/accounts/${account.id}`, { headers: auth(tok) });
    }
  });

  test('delete account from detail view — account removed from list', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const createRes = await request.post('/accounts', {
      data: { name: 'Account To Delete' },
      headers: auth(tok),
    });
    const account = await createRes.json();

    await reloadDashboard(page);
    await page.getByRole('button', { name: 'Accounts' }).click();
    await expect(page.getByRole('cell', { name: 'Account To Delete' })).toBeVisible({ timeout: 8_000 });
    await page.getByRole('button', { name: 'Account To Delete' }).first().click();
    await expect(page.getByRole('heading', { name: 'Account To Delete' })).toBeVisible({ timeout: 5_000 });

    // window.confirm dialog
    page.once('dialog', (d) => void d.accept());
    await page.getByRole('button', { name: 'Delete' }).click();

    // Returns to accounts list after deletion
    await expect(page.getByRole('button', { name: 'New Account' })).toBeVisible({ timeout: 8_000 });
    await expect(page.getByRole('cell', { name: 'Account To Delete' })).not.toBeVisible();

    // Verify via API
    const goneRes = await request.get(`/accounts/${account.id}`, { headers: auth(tok) });
    expect(goneRes.status()).toBe(404);
  });

  test('accounts - detail shows linked contacts section', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const createRes = await request.post('/accounts', {
      data: { name: 'FC Accounts Detail', domain: 'fcdetail.example.com', industry: 'Technology' },
      headers: auth(tok),
    });
    expect(createRes.ok()).toBeTruthy();
    const account = await createRes.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Accounts' }).click();
      await expect(page.getByRole('cell', { name: 'FC Accounts Detail' })).toBeVisible({ timeout: 8_000 });

      // Click the account name button to open the detail view
      await page.getByRole('button', { name: 'FC Accounts Detail' }).first().click();
      await expect(page.getByRole('heading', { name: 'FC Accounts Detail' })).toBeVisible({ timeout: 5_000 });

      // Linked Contacts section header must be present whether or not contacts are linked
      await expect(page.getByRole('heading', { name: 'Linked Contacts' })).toBeVisible();
      // Empty-state message is shown when no contacts are linked to this account
      await expect(page.getByText('No linked contacts.')).toBeVisible();
    } finally {
      await request.delete(`/accounts/${account.id}`, { headers: auth(tok) });
    }
  });
});
