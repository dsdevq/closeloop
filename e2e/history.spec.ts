/**
 * CloseLoop CRM — Entity Timeline e2e tests
 *
 * Covers: timeline panel on deal, contact, and activity detail views.
 * The panel renders history entries fetched from GET /history?entity_type=...
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

// ── Deal timeline ─────────────────────────────────────────────────────────────

test.describe('Deal timeline', () => {
  test('deal detail view shows History panel with deal_created entry', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const runTag = Date.now().toString(36).slice(-5);
    const contactName = `History Deal Contact ${runTag}`;
    const dealTitle = `History Timeline Deal ${runTag}`;

    const cRes = await request.post('/contacts', {
      data: { name: contactName },
      headers: auth(tok),
    });
    expect(cRes.ok()).toBeTruthy();
    const contact = await cRes.json();

    const stagesRes = await request.get('/pipeline/stages', { headers: auth(tok) });
    const stages: { id: number }[] = await stagesRes.json();
    const stageId = stages[0]?.id;

    const dRes = await request.post('/deals', {
      data: { title: dealTitle, contact_id: contact.id, value: 1000, stage_id: stageId },
      headers: auth(tok),
    });
    expect(dRes.ok()).toBeTruthy();
    const deal = await dRes.json();

    try {
      await reloadDashboard(page);
      await page.getByText(dealTitle).first().click();

      await expect(page.getByRole('heading', { name: dealTitle })).toBeVisible({ timeout: 5_000 });

      // Timeline panel heading — exact: true avoids matching entity h1 titles that start with "History"
      await expect(page.getByRole('heading', { name: 'History', exact: true })).toBeVisible({ timeout: 8_000 });

      // The deal_created entry label
      await expect(page.getByText(`Deal created: ${dealTitle}`)).toBeVisible({ timeout: 8_000 });
    } finally {
      await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });

  test('deal timeline shows stage_changed entry after stage move', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const runTag = Date.now().toString(36).slice(-5);
    const contactName = `History Stage Contact ${runTag}`;
    const dealTitle = `History Stage Deal ${runTag}`;

    const cRes = await request.post('/contacts', {
      data: { name: contactName },
      headers: auth(tok),
    });
    const contact = await cRes.json();

    const stagesRes = await request.get('/pipeline/stages', { headers: auth(tok) });
    const stages: { id: number; name: string }[] = await stagesRes.json();
    expect(stages.length).toBeGreaterThanOrEqual(2);
    const srcStage = stages[0];
    const dstStage = stages[1];

    const dRes = await request.post('/deals', {
      data: { title: dealTitle, contact_id: contact.id, value: 500, stage_id: srcStage.id },
      headers: auth(tok),
    });
    const deal = await dRes.json();

    // Move the deal to the second stage via API
    await request.patch(`/deals/${deal.id}`, {
      data: { stage_id: dstStage.id },
      headers: auth(tok),
    });

    try {
      await reloadDashboard(page);
      await page.getByText(dealTitle).first().click();

      await expect(page.getByRole('heading', { name: 'History', exact: true })).toBeVisible({ timeout: 8_000 });
      // .first() guards against multiple matching entries when SQLite reuses entity IDs
      // across test runs (history entries survive entity deletion by design — ADR-0026).
      await expect(
        page.getByText(new RegExp(`Stage changed.*${dstStage.name}`)).first(),
      ).toBeVisible({ timeout: 8_000 });
    } finally {
      await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });
});

// ── Contact timeline ──────────────────────────────────────────────────────────

test.describe('Contact timeline', () => {
  test('contact detail view shows History panel with contact_created entry', async ({
    page,
    request,
  }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const runTag = Date.now().toString(36).slice(-5);
    const contactName = `History Contact ${runTag}`;

    const cRes = await request.post('/contacts', {
      data: { name: contactName },
      headers: auth(tok),
    });
    expect(cRes.ok()).toBeTruthy();
    const contact = await cRes.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Contacts' }).click();
      await expect(page.getByRole('cell', { name: contactName })).toBeVisible({ timeout: 10_000 });
      await page.getByRole('button', { name: contactName }).click();

      await expect(page.getByRole('heading', { name: contactName })).toBeVisible({ timeout: 5_000 });
      await expect(page.getByRole('heading', { name: 'History', exact: true })).toBeVisible({ timeout: 8_000 });
      await expect(
        page.getByText(`Contact created: ${contactName}`),
      ).toBeVisible({ timeout: 8_000 });
    } finally {
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });
});

// ── Activity timeline ─────────────────────────────────────────────────────────

test.describe('Activity timeline', () => {
  test('activity detail view shows History panel with activity_created entry', async ({
    page,
    request,
  }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const runTag = Date.now().toString(36).slice(-5);
    const activityTitle = `History Activity ${runTag}`;

    const aRes = await request.post('/activities', {
      data: { type: 'call', title: activityTitle },
      headers: auth(tok),
    });
    expect(aRes.ok()).toBeTruthy();
    const activity = await aRes.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Activities' }).click();
      await expect(page.getByRole('button', { name: activityTitle })).toBeVisible({ timeout: 10_000 });
      await page.getByRole('button', { name: activityTitle }).click();

      await expect(page.getByRole('heading', { name: activityTitle })).toBeVisible({ timeout: 5_000 });
      await expect(page.getByRole('heading', { name: 'History', exact: true })).toBeVisible({ timeout: 8_000 });
      await expect(
        page.getByText(`Call logged: ${activityTitle}`),
      ).toBeVisible({ timeout: 8_000 });
    } finally {
      await request.delete(`/activities/${activity.id}`, { headers: auth(tok) });
    }
  });
});
