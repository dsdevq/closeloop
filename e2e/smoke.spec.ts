/**
 * CloseLoop CRM — Playwright smoke-test suite
 *
 * Covers: basic load, auth, navigation, Contacts/Deals/Accounts/Activities CRUD,
 * CSV import, CSV export.
 *
 * Tests tagged "[UI gap]" are EXPECTED TO FAIL — they document UI features that
 * exist in the API but have no corresponding button/page in the current SPA.
 * These failures are the defect catalogue for the next sprint.
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

// ── Auth helpers ──────────────────────────────────────────────────────────────

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

// ── 3. Navigation ─────────────────────────────────────────────────────────────

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await loginAndWait(page);
  });

  const NAV_TABS = ['Pipeline', 'Contacts', 'Accounts', 'Today', 'Stats'] as const;

  for (const tab of NAV_TABS) {
    test(`"${tab}" tab is clickable and renders non-blank content`, async ({ page }) => {
      await page.getByRole('button', { name: tab }).click();
      const main = page.locator('main');
      await expect(main).toBeVisible();
      const text = await main.textContent();
      expect((text ?? '').trim().length).toBeGreaterThan(0);
    });
  }
});

// ── 4. Contacts CRUD ──────────────────────────────────────────────────────────

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

  // TODO: implement per-contact detail/edit page in SPA
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
});

// ── 5. Deals CRUD ─────────────────────────────────────────────────────────────

test.describe('Deals CRUD', () => {
  test('create deal via New Deal modal — card appears in kanban board', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    // Use a unique name per run so stale data from prior runs never causes strict-mode
    // violations when we wait for the contact cell to appear.
    const runTag = Date.now().toString(36).slice(-5);
    const contactName = `Deal Modal Contact ${runTag}`;
    const dealTitle = `Smoke Kanban Deal ${runTag}`;

    // Create a contact so the deal modal dropdown has an option
    const contactRes = await request.post('/contacts', {
      data: { name: contactName },
      headers: auth(tok),
    });
    expect(contactRes.ok()).toBeTruthy();
    const contact = await contactRes.json();

    try {
      // Reload so the React state picks up the newly created contact.
      // Then visit the Contacts tab and wait for the contact row to appear —
      // this confirms refreshCore() has finished and the contact is in state
      // before we try to select it in the Deal modal dropdown.
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Contacts' }).click();
      await expect(page.getByRole('cell', { name: contactName })).toBeVisible({
        timeout: 10_000,
      });
      await page.getByRole('button', { name: 'Pipeline' }).click();

      await page.getByRole('button', { name: 'New Deal' }).first().click();
      await expect(page.getByRole('heading', { name: 'New Deal' })).toBeVisible();

      await page.getByLabel('Title').fill(dealTitle);
      await page.getByLabel('Contact').selectOption({ label: contactName });
      await page.getByLabel('Value').fill('5000');
      await page.getByRole('button', { name: 'Create' }).click();

      // Bug: newly-created deals have stage_id=null so they never match any kanban column.
      // This assertion FAILS as a defect marker for the missing stage_id assignment on POST /deals.
      await expect(page.getByText(dealTitle)).toBeVisible({ timeout: 8_000 });
    } finally {
      // Cleanup runs even if the kanban assertion above fails
      const deals: { id: number; title: string }[] = await (
        await request.get('/deals', { headers: auth(tok) })
      ).json();
      const deal = deals.find((d) => d.title === dealTitle);
      if (deal) await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });

  // TODO: implement per-deal detail/edit page in SPA
  test.fixme('deal detail/edit UI [UI gap — no per-deal detail page in SPA]', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const cRes = await request.post('/contacts', {
      data: { name: 'Deal Gap Contact' },
      headers: auth(tok),
    });
    const contact = await cRes.json();
    const dRes = await request.post('/deals', {
      data: { title: 'Gap Test Deal', contact_id: contact.id, value: 100 },
      headers: auth(tok),
    });
    const deal = await dRes.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Pipeline' }).click();
      await expect(page.getByText('Gap Test Deal')).toBeVisible({ timeout: 8_000 });

      // Clicking the deal card should open a detail view — no such UI exists.
      // This test FAILS as a defect marker for the missing deal-detail page.
      await page.getByText('Gap Test Deal').first().click();
      await expect(page.getByRole('heading', { name: /Gap Test Deal/i })).toBeVisible({
        timeout: 3_000,
      });
    } finally {
      await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });

  test('edit deal via API — PATCH /deals/:id', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const cRes = await request.post('/contacts', { data: { name: 'Deal Edit Contact' }, headers: auth(tok) });
    const contact = await cRes.json();
    const dRes = await request.post('/deals', {
      data: { title: 'API Edit Deal', contact_id: contact.id, value: 100 },
      headers: auth(tok),
    });
    expect(dRes.ok()).toBeTruthy();
    const deal = await dRes.json();

    try {
      const editRes = await request.patch(`/deals/${deal.id}`, {
        data: { value: 9999 },
        headers: auth(tok),
      });
      expect(editRes.ok()).toBeTruthy();
      expect(Number((await editRes.json()).value)).toBe(9999);
    } finally {
      await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });

  test('delete deal via API — DELETE /deals/:id returns 404 after deletion', async ({
    page,
    request,
  }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const cRes = await request.post('/contacts', { data: { name: 'Deal Del Contact' }, headers: auth(tok) });
    const contact = await cRes.json();
    const dRes = await request.post('/deals', {
      data: { title: 'API Delete Deal', contact_id: contact.id, value: 1 },
      headers: auth(tok),
    });
    expect(dRes.ok()).toBeTruthy();
    const deal = await dRes.json();

    try {
      const delRes = await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
      expect(delRes.ok()).toBeTruthy();

      const goneRes = await request.get(`/deals/${deal.id}`, { headers: auth(tok) });
      expect(goneRes.status()).toBe(404);
    } finally {
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });
});

// ── 6. Accounts CRUD ──────────────────────────────────────────────────────────

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

  // TODO: add edit form/button to account detail view
  test.fixme('edit account [UI gap — no edit form in account detail view]', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);
    const createRes = await request.post('/accounts', {
      data: { name: 'Edit Gap Account' },
      headers: auth(tok),
    });
    const account = await createRes.json();

    try {
      await reloadDashboard(page);
      await page.getByRole('button', { name: 'Accounts' }).click();
      await page.getByRole('button', { name: 'Edit Gap Account' }).first().click();
      await expect(page.getByRole('heading', { name: 'Edit Gap Account' })).toBeVisible({ timeout: 5_000 });

      // No edit form/button exists in the account detail view — defect marker
      await page.getByRole('button', { name: /edit/i }).click({ timeout: 3_000 });
      await expect(page.getByRole('heading', { name: /edit/i })).toBeVisible({ timeout: 3_000 });
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
});

// ── 7. Activities CRUD (API-only — no Activities tab in current SPA) ──────────

test.describe('Activities CRUD', () => {
  test('full CRUD lifecycle via REST API', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const cRes = await request.post('/contacts', {
      data: { name: 'Activity Test Contact' },
      headers: auth(tok),
    });
    const contact = await cRes.json();

    try {
      // CREATE
      const createRes = await request.post('/activities', {
        data: { title: 'Smoke Call', type: 'call', contact_id: contact.id, body: 'Initial note' },
        headers: auth(tok),
      });
      expect(createRes.ok()).toBeTruthy();
      const activity = await createRes.json();
      expect(activity.title).toBe('Smoke Call');
      expect(activity.type).toBe('call');

      // LIST
      const listRes = await request.get('/activities', { headers: auth(tok) });
      expect(listRes.ok()).toBeTruthy();
      const list: { id: number }[] = await listRes.json();
      expect(list.some((a) => a.id === activity.id)).toBeTruthy();

      // GET by ID
      const getRes = await request.get(`/activities/${activity.id}`, { headers: auth(tok) });
      expect(getRes.ok()).toBeTruthy();
      expect((await getRes.json()).id).toBe(activity.id);

      // PATCH
      const patchRes = await request.patch(`/activities/${activity.id}`, {
        data: { body: 'Updated note' },
        headers: auth(tok),
      });
      expect(patchRes.ok()).toBeTruthy();
      expect((await patchRes.json()).body).toBe('Updated note');

      // DELETE
      const delRes = await request.delete(`/activities/${activity.id}`, { headers: auth(tok) });
      expect(delRes.ok()).toBeTruthy();

      // 404 after deletion
      const goneRes = await request.get(`/activities/${activity.id}`, { headers: auth(tok) });
      expect(goneRes.status()).toBe(404);
    } finally {
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });

  // TODO: add Activities nav tab and list view to SPA
  test.fixme('Activities navigation tab [UI gap — no Activities tab in current SPA]', async ({ page }) => {
    await loginAndWait(page);
    // Expected to FAIL: the SPA has no Activities tab — defect marker
    await expect(page.getByRole('button', { name: 'Activities' })).toBeVisible({ timeout: 3_000 });
  });
});

// ── 8. Import flow ────────────────────────────────────────────────────────────

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

  // TODO: add CSV import button/modal to Contacts view
  test.fixme('import UI trigger [UI gap — no import button in current SPA]', async ({ page }) => {
    await loginAndWait(page);
    // Expected to FAIL: the SPA has no import button/modal — defect marker
    const trigger = page
      .getByRole('button', { name: /import/i })
      .or(page.getByRole('link', { name: /import/i }));
    await expect(trigger).toBeVisible({ timeout: 3_000 });
  });
});

// ── 9. Export flow ────────────────────────────────────────────────────────────

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

  // TODO: add CSV export button to Contacts view
  test.fixme('export UI trigger [UI gap — no export button in current SPA]', async ({ page }) => {
    await loginAndWait(page);
    // Expected to FAIL: the SPA has no export button — defect marker
    const trigger = page
      .getByRole('button', { name: /export/i })
      .or(page.getByRole('link', { name: /export/i }));
    await expect(trigger).toBeVisible({ timeout: 3_000 });
  });
});
