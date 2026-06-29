/**
 * CloseLoop CRM — Contacts e2e tests
 *
 * Covers: contacts tab navigation, Contacts CRUD (smoke + full-coverage),
 * CSV import/export, saved-view Apply/Clear, interactive modal controls.
 *
 * Tests tagged "[UI gap]" are EXPECTED TO FAIL — they document UI features that
 * exist in the API but have no corresponding button/page in the current SPA.
 *
 * Run:  npx playwright test --reporter=list
 * Env:  TEST_USER / TEST_PASS (defaults: admin@closeloop.com / admin123)
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

  test('"Contacts" tab is clickable and renders non-blank content', async ({ page }) => {
    await page.getByRole('button', { name: 'Contacts' }).click();
    const main = page.locator('main');
    await expect(main).toBeVisible();
    const text = await main.textContent();
    expect((text ?? '').trim().length).toBeGreaterThan(0);
  });
});

// ── Interactive controls ──────────────────────────────────────────────────────

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

// ── Contacts CRUD (smoke) ─────────────────────────────────────────────────────

test.describe('Contacts CRUD', () => {
  test('create contact via New Contact modal — appears in contacts table', async ({ page, request }) => {
    await loginAndWait(page);
    await page.getByRole('button', { name: 'Contacts' }).click();
    await page.getByRole('button', { name: 'New Contact' }).click();

    await expect(page.getByRole('heading', { name: 'New Contact' })).toBeVisible();
    await page.getByLabel('Name').fill('Smoke UI Contact');
    await page.getByLabel('Email').fill('smoke.ui@test.internal');
    await page.getByLabel('Phone').fill('555-0001');
    await page.getByLabel('Company').fill('Smoke Labs');
    await page.getByRole('button', { name: 'Create' }).click();

    await expect(page.getByRole('cell', { name: 'Smoke UI Contact' })).toBeVisible({ timeout: 8_000 });

    // Cleanup
    const tok = await bearerToken(page);
    const list: { id: number; name: string }[] = await (
      await request.get('/contacts', { headers: auth(tok) })
    ).json();
    const c = list.find((x) => x.name === 'Smoke UI Contact');
    if (c) await request.delete(`/contacts/${c.id}`, { headers: auth(tok) });
  });

  test.fixme('contact detail/edit UI [UI gap — no per-contact detail page exists in SPA]', async ({
    page,
    request,
  }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const res = await request.post('/contacts', {
      data: { name: 'Gap Test Contact' },
      headers: auth(tok),
    });
    const contact = await res.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Contacts' }).click();
      await expect(page.getByRole('cell', { name: 'Gap Test Contact' })).toBeVisible({ timeout: 8_000 });

      // The contacts table has NO clickable link/button per row beyond the Account link.
      // Attempting to navigate to a detail page will FAIL — defect marker.
      const row = page.getByRole('row').filter({ hasText: 'Gap Test Contact' });
      const clickable = row.getByRole('button').or(row.getByRole('link'));
      await clickable.first().click({ timeout: 3_000 });
      await expect(page.getByRole('heading', { name: /Gap Test Contact/i })).toBeVisible({
        timeout: 3_000,
      });
    } finally {
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });

  test('edit contact via API — PATCH /contacts/:id', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const res = await request.post('/contacts', {
      data: { name: 'API Edit Contact', email: 'edit@test.internal' },
      headers: auth(tok),
    });
    expect(res.ok()).toBeTruthy();
    const contact = await res.json();

    try {
      const editRes = await request.patch(`/contacts/${contact.id}`, {
        data: { company: 'Patched Corp' },
        headers: auth(tok),
      });
      expect(editRes.ok()).toBeTruthy();
      expect((await editRes.json()).company).toBe('Patched Corp');
    } finally {
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });

  test('delete contact via API — DELETE /contacts/:id returns 404 after deletion', async ({
    page,
    request,
  }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const res = await request.post('/contacts', {
      data: { name: 'API Delete Contact' },
      headers: auth(tok),
    });
    expect(res.ok()).toBeTruthy();
    const contact = await res.json();

    const delRes = await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    expect(delRes.ok()).toBeTruthy();

    const goneRes = await request.get(`/contacts/${contact.id}`, { headers: auth(tok) });
    expect(goneRes.status()).toBe(404);
  });

  // ── Contacts CRUD (full-coverage) ──────────────────────────────────────────

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

// ── Import (smoke) ────────────────────────────────────────────────────────────

test.describe('Import', () => {
  test('POST /contacts/import accepts CSV body and returns imported count', async ({
    page,
    request,
  }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const csv = [
      'name,email,phone,company',
      'Import Alpha,alpha.imp@test.internal,555-1001,Alpha Inc',
      'Import Beta,beta.imp@test.internal,555-1002,Beta Inc',
    ].join('\n');

    const res = await request.post('/contacts/import', {
      data: { csv },
      headers: auth(tok),
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.imported).toBe(2);
    expect(body.errors).toHaveLength(0);

    // Cleanup imported contacts
    const contacts: { id: number; name: string }[] = await (
      await request.get('/contacts', { headers: auth(tok) })
    ).json();
    for (const name of ['Import Alpha', 'Import Beta']) {
      const c = contacts.find((x) => x.name === name);
      if (c) await request.delete(`/contacts/${c.id}`, { headers: auth(tok) });
    }
  });

  test.fixme('import UI trigger [UI gap — no import button in current SPA]', async ({ page }) => {
    await loginAndWait(page);
    // Expected to FAIL: the SPA has no import button/modal — defect marker
    const trigger = page
      .getByRole('button', { name: /import/i })
      .or(page.getByRole('link', { name: /import/i }));
    await expect(trigger).toBeVisible({ timeout: 3_000 });
  });
});

// ── Export (smoke) ────────────────────────────────────────────────────────────

test.describe('Export', () => {
  test('GET /contacts/export returns text/csv with expected column headers', async ({
    page,
    request,
  }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const res = await request.get('/contacts/export', { headers: auth(tok) });
    expect(res.ok()).toBeTruthy();
    expect(res.headers()['content-type']).toContain('text/csv');
    const csv = await res.text();
    // Verify the CSV header row contains expected columns
    expect(csv).toContain('name');
    expect(csv).toContain('email');
    expect(csv).toContain('id');
  });

  test.fixme('export UI trigger [UI gap — no export button in current SPA]', async ({ page }) => {
    await loginAndWait(page);
    // Expected to FAIL: the SPA has no export button — defect marker
    const trigger = page
      .getByRole('button', { name: /export/i })
      .or(page.getByRole('link', { name: /export/i }));
    await expect(trigger).toBeVisible({ timeout: 3_000 });
  });
});

// ── Import / Export (full-coverage) ──────────────────────────────────────────

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

// ── Extended interactive controls (contacts) ──────────────────────────────────

test.describe('Extended interactive controls', () => {
  test('contacts - saved-view Apply filters the list', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const runTag = Date.now().toString(36).slice(-6);

    const companyMatch = `FC-M-${runTag}`;
    const matchName = `FC ViewApply Match ${runTag}`;
    const noMatchName = `FC ViewApply NoMatch ${runTag}`;

    const cMatchRes = await request.post('/contacts', {
      data: { name: matchName, company: companyMatch },
      headers: auth(tok),
    });
    const cMatch = await cMatchRes.json();

    const cNoMatchRes = await request.post('/contacts', {
      data: { name: noMatchName, company: `FC-X-${runTag}` },
      headers: auth(tok),
    });
    const cNoMatch = await cNoMatchRes.json();

    // Create a saved view that filters by exact company value
    const viewRes = await request.post('/saved-views', {
      data: {
        name: `FC ViewApply ${runTag}`,
        entity_type: 'contacts',
        filter_expr: { op: 'eq', field: 'company', value: companyMatch },
      },
      headers: auth(tok),
    });
    const view = await viewRes.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Contacts' }).click();

      // Both contacts visible before any view is applied
      await expect(page.getByRole('button', { name: matchName })).toBeVisible({ timeout: 8_000 });
      await expect(page.getByRole('button', { name: noMatchName })).toBeVisible({ timeout: 5_000 });

      // Apply the saved view by clicking its button in the SavedViewsBar
      await page.getByRole('button', { name: `FC ViewApply ${runTag}` }).click();

      // Only the matching contact is shown; non-matching contact is gone
      await expect(page.getByRole('button', { name: matchName })).toBeVisible({ timeout: 8_000 });
      await expect(page.getByRole('button', { name: noMatchName })).not.toBeVisible({ timeout: 5_000 });

      // Active view indicator is displayed
      await expect(page.getByText(`Showing: FC ViewApply ${runTag}`)).toBeVisible();
    } finally {
      await request.delete(`/contacts/${cMatch.id}`, { headers: auth(tok) });
      await request.delete(`/contacts/${cNoMatch.id}`, { headers: auth(tok) });
      await request.delete(`/saved-views/${view.id}`, { headers: auth(tok) });
    }
  });

  test('contacts - saved-view Clear resets the list', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const runTag = Date.now().toString(36).slice(-6);

    const companyMatch = `FC-M-${runTag}`;
    const matchName = `FC ViewClear Match ${runTag}`;
    const noMatchName = `FC ViewClear NoMatch ${runTag}`;

    const cMatchRes = await request.post('/contacts', {
      data: { name: matchName, company: companyMatch },
      headers: auth(tok),
    });
    const cMatch = await cMatchRes.json();

    const cNoMatchRes = await request.post('/contacts', {
      data: { name: noMatchName, company: `FC-X-${runTag}` },
      headers: auth(tok),
    });
    const cNoMatch = await cNoMatchRes.json();

    const viewRes = await request.post('/saved-views', {
      data: {
        name: `FC ViewClear ${runTag}`,
        entity_type: 'contacts',
        filter_expr: { op: 'eq', field: 'company', value: companyMatch },
      },
      headers: auth(tok),
    });
    const view = await viewRes.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Contacts' }).click();

      // Apply the view first (prerequisites for testing Clear)
      await page.getByRole('button', { name: `FC ViewClear ${runTag}` }).click();
      await expect(page.getByRole('button', { name: matchName })).toBeVisible({ timeout: 8_000 });
      await expect(page.getByRole('button', { name: noMatchName })).not.toBeVisible({ timeout: 5_000 });

      // Click Clear (exact match to avoid substring collisions with saved-view button names)
      await page.getByRole('button', { name: 'Clear', exact: true }).click();

      // Both contacts should be visible again (full unfiltered list restored)
      await expect(page.getByRole('button', { name: matchName })).toBeVisible({ timeout: 5_000 });
      await expect(page.getByRole('button', { name: noMatchName })).toBeVisible({ timeout: 5_000 });

      // Active view indicator is gone
      await expect(page.getByText(`Showing: FC ViewClear ${runTag}`)).not.toBeVisible();
    } finally {
      await request.delete(`/contacts/${cMatch.id}`, { headers: auth(tok) });
      await request.delete(`/contacts/${cNoMatch.id}`, { headers: auth(tok) });
      await request.delete(`/saved-views/${view.id}`, { headers: auth(tok) });
    }
  });
});
