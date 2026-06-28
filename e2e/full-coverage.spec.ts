/**
 * CloseLoop CRM — full-coverage Playwright test suite
 *
 * Covers: route coverage, interactive controls, Contacts/Deals/Activities CRUD,
 * Import/Export, Auth flows.
 *
 * All 22+ tests must pass under: npx playwright test --reporter=list
 * Env: TEST_USER / TEST_PASS (defaults: admin@closeloop.com / admin123)
 */

import path from 'path';
import { test as base, expect, type Page } from '@playwright/test';

// ── Auto-fixture: collect JS errors and fail the test if any occurred ──────────
const test = base.extend<{ _jsGuard: void }>({
  _jsGuard: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on('pageerror', (err) => errors.push(`Uncaught: ${err.message}`));
      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          // Skip browser-generated fetch error messages (e.g. from intentional 401 tests)
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

// ── ROUTE COVERAGE ────────────────────────────────────────────────────────────

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

// ── INTERACTIVE CONTROLS ──────────────────────────────────────────────────────

test.describe('Interactive controls', () => {
  test('interactive controls are reachable', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await loginAndWait(page);
    await page.getByRole('button', { name: 'Contacts' }).click();

    // Open New Contact modal
    await page.getByRole('button', { name: 'New Contact' }).click();
    await expect(page.getByRole('heading', { name: 'New Contact' })).toBeVisible({ timeout: 5_000 });

    // Dismiss with Cancel
    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('heading', { name: 'New Contact' })).not.toBeVisible({ timeout: 5_000 });

    expect(errors, 'No uncaught JS exceptions').toHaveLength(0);
  });
});

// ── CONTACTS CRUD ─────────────────────────────────────────────────────────────

test.describe('Contacts CRUD', () => {
  test('contacts - list', async ({ page }) => {
    await loginAndWait(page);
    await page.getByRole('button', { name: 'Contacts' }).click();
    // Either the table header or the empty-state is visible
    await expect(
      page.getByRole('columnheader', { name: 'Name' })
    ).toBeVisible({ timeout: 8_000 });
  });

  test('contacts - create', async ({ page, request }) => {
    await loginAndWait(page);
    await page.getByRole('button', { name: 'Contacts' }).click();
    await page.getByRole('button', { name: 'New Contact' }).click();

    await expect(page.getByRole('heading', { name: 'New Contact' })).toBeVisible();
    await page.getByLabel('Name').fill('FC Create Contact');
    await page.getByLabel('Email').fill('fc.create@test.internal');
    await page.getByLabel('Phone').fill('555-0010');
    await page.getByLabel('Company').fill('FC Corp');
    await page.getByRole('button', { name: 'Create' }).click();

    await expect(page.getByRole('cell', { name: 'FC Create Contact' })).toBeVisible({ timeout: 8_000 });

    // Cleanup
    const tok = await bearerToken(page);
    const list: { id: number; name: string }[] = await (
      await request.get('/contacts', { headers: auth(tok) })
    ).json();
    const c = list.find((x) => x.name === 'FC Create Contact');
    if (c) await request.delete(`/contacts/${c.id}`, { headers: auth(tok) });
  });

  test('contacts - detail', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const res = await request.post('/contacts', {
      data: { name: 'FC Detail Contact', email: 'fc.detail@test.internal', phone: '555-1111', company: 'Detail Corp' },
      headers: auth(tok),
    });
    expect(res.ok()).toBeTruthy();
    const contact = await res.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Contacts' }).click();
      await expect(page.getByRole('cell', { name: 'FC Detail Contact' })).toBeVisible({ timeout: 8_000 });

      // Click the contact name to open detail view
      await page.getByRole('button', { name: 'FC Detail Contact' }).click();

      await expect(page.getByRole('heading', { name: 'FC Detail Contact' })).toBeVisible({ timeout: 5_000 });
      await expect(page.getByText('555-1111')).toBeVisible();
      await expect(page.getByText('Detail Corp')).toBeVisible();
    } finally {
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });

  test('contacts - update', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const res = await request.post('/contacts', {
      data: { name: 'FC Update Contact', company: 'Old Corp' },
      headers: auth(tok),
    });
    expect(res.ok()).toBeTruthy();
    const contact = await res.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Contacts' }).click();
      await expect(page.getByRole('cell', { name: 'FC Update Contact' })).toBeVisible({ timeout: 8_000 });

      await page.getByRole('button', { name: 'FC Update Contact' }).click();
      await expect(page.getByRole('heading', { name: 'FC Update Contact' })).toBeVisible({ timeout: 5_000 });

      // Open edit modal
      await page.getByRole('button', { name: 'Edit' }).click();
      await expect(page.getByRole('heading', { name: 'Edit Contact' })).toBeVisible({ timeout: 5_000 });

      await page.getByLabel('Company').fill('New Corp');
      await page.getByRole('button', { name: 'Save' }).click();

      // Updated value appears in detail view
      await expect(page.getByText('New Corp')).toBeVisible({ timeout: 5_000 });
    } finally {
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });

  test('contacts - delete', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const res = await request.post('/contacts', {
      data: { name: 'FC Delete Contact' },
      headers: auth(tok),
    });
    expect(res.ok()).toBeTruthy();
    const contact = await res.json();

    await reloadDashboard(page);
    await page.getByRole('button', { name: 'Contacts' }).click();
    await expect(page.getByRole('cell', { name: 'FC Delete Contact' })).toBeVisible({ timeout: 8_000 });

    await page.getByRole('button', { name: 'FC Delete Contact' }).click();
    await expect(page.getByRole('heading', { name: 'FC Delete Contact' })).toBeVisible({ timeout: 5_000 });

    // Handle window.confirm dialog
    page.once('dialog', (d) => void d.accept());
    await page.getByRole('button', { name: 'Delete' }).click();

    // Returns to contacts list
    await expect(page.getByRole('button', { name: 'New Contact' })).toBeVisible({ timeout: 8_000 });
    await expect(page.getByText('FC Delete Contact')).not.toBeVisible();

    // Verify deletion via API
    const goneRes = await request.get(`/contacts/${contact.id}`, { headers: auth(tok) });
    expect(goneRes.status()).toBe(404);
  });
});

// ── DEALS CRUD ────────────────────────────────────────────────────────────────

test.describe('Deals CRUD', () => {
  test('deals - list', async ({ page }) => {
    await loginAndWait(page);
    // Pipeline is the default tab – kanban board must be present
    await expect(page.getByRole('button', { name: 'New Deal' }).first()).toBeVisible({ timeout: 8_000 });
  });

  test('deals - create', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const runTag = Date.now().toString(36).slice(-5);
    const contactName = `FC Deal Contact ${runTag}`;
    const dealTitle = `FC Create Deal ${runTag}`;

    const contactRes = await request.post('/contacts', {
      data: { name: contactName },
      headers: auth(tok),
    });
    expect(contactRes.ok()).toBeTruthy();
    const contact = await contactRes.json();

    try {
      await reloadDashboard(page);
      // Navigate to Contacts tab first so the contact is loaded in state
      await page.getByRole('button', { name: 'Contacts' }).click();
      await expect(page.getByRole('cell', { name: contactName })).toBeVisible({ timeout: 10_000 });
      await page.getByRole('button', { name: 'Pipeline' }).click();

      await page.getByRole('button', { name: 'New Deal' }).first().click();
      await expect(page.getByRole('heading', { name: 'New Deal' })).toBeVisible();

      await page.getByLabel('Title').fill(dealTitle);
      await page.getByLabel('Contact').selectOption({ label: contactName });
      await page.getByLabel('Value').fill('7500');
      await page.getByRole('button', { name: 'Create' }).click();

      await expect(page.getByText(dealTitle)).toBeVisible({ timeout: 8_000 });
    } finally {
      const deals: { id: number; title: string }[] = await (
        await request.get('/deals', { headers: auth(tok) })
      ).json();
      const deal = deals.find((d) => d.title === dealTitle);
      if (deal) await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });

  test('deals - detail', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const cRes = await request.post('/contacts', {
      data: { name: 'FC Deal Detail Contact' },
      headers: auth(tok),
    });
    const contact = await cRes.json();

    const stagesRes = await request.get('/pipeline/stages', { headers: auth(tok) });
    const stages: { id: number }[] = await stagesRes.json();
    const stageId = stages[0]?.id;

    const dRes = await request.post('/deals', {
      data: { title: 'FC Detail Deal', contact_id: contact.id, value: 9999, stage_id: stageId },
      headers: auth(tok),
    });
    expect(dRes.ok()).toBeTruthy();
    const deal = await dRes.json();

    try {
      await reloadDashboard(page);
      // Click on the deal card
      await page.getByText('FC Detail Deal').first().click();

      await expect(page.getByRole('heading', { name: 'FC Detail Deal' })).toBeVisible({ timeout: 5_000 });
      await expect(page.getByText('$9,999')).toBeVisible();
    } finally {
      await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });

  test('deals - update', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const cRes = await request.post('/contacts', {
      data: { name: 'FC Deal Update Contact' },
      headers: auth(tok),
    });
    const contact = await cRes.json();

    const stagesRes = await request.get('/pipeline/stages', { headers: auth(tok) });
    const stages: { id: number }[] = await stagesRes.json();
    const stageId = stages[0]?.id;

    const dRes = await request.post('/deals', {
      data: { title: 'FC Update Deal', contact_id: contact.id, value: 1000, stage_id: stageId },
      headers: auth(tok),
    });
    expect(dRes.ok()).toBeTruthy();
    const deal = await dRes.json();

    try {
      await reloadDashboard(page);
      await page.getByText('FC Update Deal').first().click();
      await expect(page.getByRole('heading', { name: 'FC Update Deal' })).toBeVisible({ timeout: 5_000 });

      await page.getByRole('button', { name: 'Edit' }).click();
      await expect(page.getByRole('heading', { name: 'Edit Deal' })).toBeVisible({ timeout: 5_000 });

      await page.getByLabel('Value').fill('88888');
      await page.getByRole('button', { name: 'Save' }).click();

      await expect(page.getByText('$88,888')).toBeVisible({ timeout: 5_000 });
    } finally {
      await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });

  test('deals - delete', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const cRes = await request.post('/contacts', {
      data: { name: 'FC Deal Delete Contact' },
      headers: auth(tok),
    });
    const contact = await cRes.json();

    const stagesRes = await request.get('/pipeline/stages', { headers: auth(tok) });
    const stages: { id: number }[] = await stagesRes.json();
    const stageId = stages[0]?.id;

    const dRes = await request.post('/deals', {
      data: { title: 'FC Delete Deal', contact_id: contact.id, value: 1, stage_id: stageId },
      headers: auth(tok),
    });
    expect(dRes.ok()).toBeTruthy();
    const deal = await dRes.json();

    await reloadDashboard(page);
    await page.getByText('FC Delete Deal').first().click();
    await expect(page.getByRole('heading', { name: 'FC Delete Deal' })).toBeVisible({ timeout: 5_000 });

    page.once('dialog', (d) => void d.accept());
    await page.getByRole('button', { name: 'Delete' }).click();

    // Returns to pipeline kanban
    await expect(page.getByRole('button', { name: 'New Deal' }).first()).toBeVisible({ timeout: 8_000 });
    await expect(page.getByText('FC Delete Deal')).not.toBeVisible();

    const goneRes = await request.get(`/deals/${deal.id}`, { headers: auth(tok) });
    expect(goneRes.status()).toBe(404);

    await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
  });
});

// ── ACTIVITIES CRUD ───────────────────────────────────────────────────────────

test.describe('Activities CRUD', () => {
  test('activities - list', async ({ page }) => {
    await loginAndWait(page);
    await page.getByRole('button', { name: 'Activities' }).click();
    // The Activities table always has a Title column header
    await expect(page.getByRole('columnheader', { name: 'Title' })).toBeVisible({ timeout: 8_000 });
  });

  test('activities - create', async ({ page, request }) => {
    await loginAndWait(page);
    await page.getByRole('button', { name: 'Activities' }).click();
    await page.getByRole('button', { name: 'New Activity' }).click();

    await expect(page.getByRole('heading', { name: 'New Activity' })).toBeVisible();
    await page.getByLabel('Title').fill('FC Create Activity');
    await page.locator('select').filter({ hasText: /call/i }).selectOption('note');
    await page.getByLabel('Notes').fill('test body text');
    await page.getByRole('button', { name: 'Create' }).click();

    await expect(page.getByRole('cell', { name: 'FC Create Activity' })).toBeVisible({ timeout: 8_000 });

    // Cleanup
    const tok = await bearerToken(page);
    const list: { id: number; title: string }[] = await (
      await request.get('/activities', { headers: auth(tok) })
    ).json();
    const a = list.find((x) => x.title === 'FC Create Activity');
    if (a) await request.delete(`/activities/${a.id}`, { headers: auth(tok) });
  });

  test('activities - detail', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const res = await request.post('/activities', {
      data: { title: 'FC Detail Activity', type: 'call', body: 'detail body text' },
      headers: auth(tok),
    });
    expect(res.ok()).toBeTruthy();
    const activity = await res.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Activities' }).click();
      await expect(page.getByRole('cell', { name: 'FC Detail Activity' })).toBeVisible({ timeout: 8_000 });

      // Click the activity title button
      await page.getByRole('button', { name: 'FC Detail Activity' }).click();

      await expect(page.getByRole('heading', { name: 'FC Detail Activity' })).toBeVisible({ timeout: 5_000 });
      await expect(page.getByText('detail body text')).toBeVisible();
    } finally {
      await request.delete(`/activities/${activity.id}`, { headers: auth(tok) });
    }
  });

  test('activities - update', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const res = await request.post('/activities', {
      data: { title: 'FC Update Activity', type: 'email', body: 'original body' },
      headers: auth(tok),
    });
    expect(res.ok()).toBeTruthy();
    const activity = await res.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Activities' }).click();
      await expect(page.getByRole('cell', { name: 'FC Update Activity' })).toBeVisible({ timeout: 8_000 });

      await page.getByRole('button', { name: 'FC Update Activity' }).click();
      await expect(page.getByRole('heading', { name: 'FC Update Activity' })).toBeVisible({ timeout: 5_000 });

      await page.getByRole('button', { name: 'Edit' }).click();
      await expect(page.getByRole('heading', { name: 'Edit Activity' })).toBeVisible({ timeout: 5_000 });

      await page.getByLabel('Notes').fill('updated body text');
      await page.getByRole('button', { name: 'Save' }).click();

      await expect(page.getByText('updated body text')).toBeVisible({ timeout: 5_000 });
    } finally {
      await request.delete(`/activities/${activity.id}`, { headers: auth(tok) });
    }
  });

  test('activities - delete', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const res = await request.post('/activities', {
      data: { title: 'FC Delete Activity', type: 'meeting' },
      headers: auth(tok),
    });
    expect(res.ok()).toBeTruthy();
    const activity = await res.json();

    await reloadDashboard(page);
    await page.getByRole('button', { name: 'Activities' }).click();
    await expect(page.getByRole('cell', { name: 'FC Delete Activity' })).toBeVisible({ timeout: 8_000 });

    await page.getByRole('button', { name: 'FC Delete Activity' }).click();
    await expect(page.getByRole('heading', { name: 'FC Delete Activity' })).toBeVisible({ timeout: 5_000 });

    page.once('dialog', (d) => void d.accept());
    await page.getByRole('button', { name: 'Delete' }).click();

    // Returns to activities list
    await expect(page.getByRole('button', { name: 'New Activity' })).toBeVisible({ timeout: 8_000 });
    await expect(page.getByText('FC Delete Activity')).not.toBeVisible();

    const goneRes = await request.get(`/activities/${activity.id}`, { headers: auth(tok) });
    expect(goneRes.status()).toBe(404);
  });
});

// ── IMPORT / EXPORT ───────────────────────────────────────────────────────────

test.describe('Import / Export', () => {
  test('import - upload triggers feedback', async ({ page, request }) => {
    await loginAndWait(page);
    await page.getByRole('button', { name: 'Contacts' }).click();

    // Open import modal
    await page.getByRole('button', { name: 'Import CSV' }).click();
    await expect(page.getByRole('heading', { name: 'Import Contacts' })).toBeVisible({ timeout: 5_000 });

    // Attach the fixture CSV file
    await page.locator('input[type="file"]').setInputFiles(
      path.join(__dirname, 'fixtures', 'contacts.csv')
    );

    // Submit (use exact match to distinguish from the "Import CSV" nav button)
    await page.getByRole('button', { name: 'Import', exact: true }).click();

    // Assert success feedback — modal switches to result view
    await expect(page.getByText(/imported \d+ contact/i)).toBeVisible({ timeout: 10_000 });

    // Cleanup imported contacts
    const tok = await bearerToken(page);
    const contacts: { id: number; name: string }[] = await (
      await request.get('/contacts', { headers: auth(tok) })
    ).json();
    for (const name of ['Alice Example', 'Bob Sample']) {
      const c = contacts.find((x) => x.name === name);
      if (c) await request.delete(`/contacts/${c.id}`, { headers: auth(tok) });
    }
  });

  test('export - download initiated', async ({ page }) => {
    await loginAndWait(page);
    await page.getByRole('button', { name: 'Contacts' }).click();
    await expect(page.getByRole('button', { name: 'Export CSV' })).toBeVisible({ timeout: 5_000 });

    // The export button triggers a blob download
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 10_000 }),
      page.getByRole('button', { name: 'Export CSV' }).click(),
    ]);

    expect(download.suggestedFilename()).toContain('.csv');
  });
});

// ── AUTH FLOW ─────────────────────────────────────────────────────────────────

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
