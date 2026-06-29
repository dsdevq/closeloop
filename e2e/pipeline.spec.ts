/**
 * CloseLoop CRM — Pipeline / Deals e2e tests
 *
 * Covers: pipeline tab navigation, Deals CRUD (smoke + full-coverage),
 * drag-and-drop, per-stage Add Deal shortcut.
 *
 * Tests tagged "[UI gap]" are EXPECTED TO FAIL — they document UI features that
 * exist in the API but have no corresponding button/page in the current SPA.
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

  test('"Pipeline" tab is clickable and renders non-blank content', async ({ page }) => {
    await page.getByRole('button', { name: 'Pipeline' }).click();
    const main = page.locator('main');
    await expect(main).toBeVisible();
    const text = await main.textContent();
    expect((text ?? '').trim().length).toBeGreaterThan(0);
  });
});

// ── Deals CRUD (smoke) ────────────────────────────────────────────────────────

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

  // ── Deals CRUD (full-coverage) ─────────────────────────────────────────────

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

// ── Extended interactive controls (pipeline) ──────────────────────────────────

test.describe('Extended interactive controls', () => {
  test('pipeline - per-stage add deal shortcut opens modal', async ({ page }) => {
    await loginAndWait(page);
    // Pipeline is the default tab; wait for per-stage "Add deal" buttons (one per stage column)
    await expect(page.getByRole('button', { name: 'Add deal' }).first()).toBeVisible({ timeout: 8_000 });

    // Click the first per-stage shortcut (footer button of the first stage column)
    await page.getByRole('button', { name: 'Add deal' }).first().click();

    // The shared New Deal modal must open
    await expect(page.getByRole('heading', { name: 'New Deal' })).toBeVisible({ timeout: 5_000 });

    // Dismiss cleanly
    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('heading', { name: 'New Deal' })).not.toBeVisible({ timeout: 3_000 });
  });

  test('pipeline - drag deal card to different stage', async ({ page, request }) => {
    await loginAndWait(page);
    const tok = await bearerToken(page);

    const stagesRes = await request.get('/pipeline/stages', { headers: auth(tok) });
    const stages: { id: number; name: string }[] = await stagesRes.json();
    expect(stages.length, 'Need at least 2 pipeline stages for drag-and-drop').toBeGreaterThanOrEqual(2);

    const srcStage = stages[0];
    const dstStage = stages[1];

    const contactRes = await request.post('/contacts', {
      data: { name: 'FC Drag Contact' },
      headers: auth(tok),
    });
    const contact = await contactRes.json();

    const dealRes = await request.post('/deals', {
      data: { title: 'FC Drag Deal', contact_id: contact.id, value: 100, stage_id: srcStage.id },
      headers: auth(tok),
    });
    expect(dealRes.ok()).toBeTruthy();
    const deal = await dealRes.json();

    try {
      await reloadDashboard(page);

      // Deal must appear in the source stage column before we drag it
      await expect(page.getByText('FC Drag Deal')).toBeVisible({ timeout: 8_000 });

      // Source: the DealCard element (rendered with draggable="true")
      const dealCard = page.locator('[draggable="true"]').filter({ hasText: 'FC Drag Deal' });

      // Destination: stage column index 1's drop zone.
      // Kanban: .flex.gap-3.overflow-x-auto.pb-3 > div  →  one div per stage (in position order).
      // Each stage column's drop zone is its second direct child <div>
      // (first = header, second = drop zone, third = <button>Add deal</button>).
      const kanban = page.locator('.flex.gap-3.overflow-x-auto.pb-3');
      const dstColumn = kanban.locator('> div').nth(1);
      const dstDropZone = dstColumn.locator('> div').nth(1);

      const patchPromise = page.waitForResponse(
        (resp) => resp.url().includes('/deals/') && resp.request().method() === 'PATCH',
        { timeout: 10_000 },
      );

      await dealCard.dragTo(dstDropZone);
      const patchResp = await patchPromise;
      expect(patchResp.ok()).toBeTruthy();

      // Confirm the stage_id was updated in the database
      const verifyRes = await request.get(`/deals/${deal.id}`, { headers: auth(tok) });
      const updated = await verifyRes.json();
      expect(updated.stage_id).toBe(dstStage.id);
    } finally {
      await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
      await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
    }
  });
});
