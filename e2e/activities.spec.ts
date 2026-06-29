/**
 * CloseLoop CRM — Activities e2e tests
 *
 * Covers: Activities CRUD (smoke API-level + full-coverage UI), activities tab navigation.
 *
 * Tests tagged "[UI gap]" are EXPECTED TO FAIL — they document UI features that
 * exist in the API but have no corresponding button/page in the current SPA.
 *
 * Run:  npx playwright test --reporter=list
 * Env:  TEST_USER / TEST_PASS (defaults: admin@closeloop.com / admin123)
 */

import { expect } from '@playwright/test';
import { test, loginAndWait, reloadDashboard, bearerToken, auth } from './helpers';

// ── Activities CRUD ───────────────────────────────────────────────────────────

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
