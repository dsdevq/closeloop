# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: smoke.spec.ts >> Activities CRUD >> Activities navigation tab [UI gap — no Activities tab in current SPA]
- Location: e2e/smoke.spec.ts:557:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByRole('button', { name: 'Activities' })
Expected: visible
Timeout: 3000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 3000ms
  - waiting for getByRole('button', { name: 'Activities' })

```

```yaml
- banner:
  - text: CloseLoop CRM
  - navigation:
    - button "Pipeline"
    - button "Contacts"
    - button "Accounts"
    - button "Today"
    - button "Stats"
  - text: Admin admin
  - button "Sign out"
- main:
  - heading "Pipeline" [level=1]
  - button "New Deal"
  - text: Saved Views No saved views Prospecting 0% probability 0
  - button "Add deal"
  - text: Qualification 20% probability 0
  - button "Add deal"
  - text: Proposal 50% probability 0
  - button "Add deal"
  - text: Negotiation 75% probability 0
  - button "Add deal"
  - text: Closed-Won 100% probability 0
  - button "Add deal"
  - text: Closed-Lost 0% probability 0
  - button "Add deal"
  - text: Weighted Forecast $1,510 open deals by stage probability
```

# Test source

```ts
  460 |       await reloadDashboard(page);
  461 |       await page.getByRole('button', { name: 'Accounts' }).click();
  462 |       await page.getByRole('button', { name: 'Edit Gap Account' }).first().click();
  463 |       await expect(page.getByRole('heading', { name: 'Edit Gap Account' })).toBeVisible({ timeout: 5_000 });
  464 | 
  465 |       // No edit form/button exists in the account detail view — defect marker
  466 |       await page.getByRole('button', { name: /edit/i }).click({ timeout: 3_000 });
  467 |       await expect(page.getByRole('heading', { name: /edit/i })).toBeVisible({ timeout: 3_000 });
  468 |     } finally {
  469 |       await request.delete(`/accounts/${account.id}`, { headers: auth(tok) });
  470 |     }
  471 |   });
  472 | 
  473 |   test('delete account from detail view — account removed from list', async ({ page, request }) => {
  474 |     await loginAndWait(page);
  475 |     const tok = await bearerToken(page);
  476 |     const createRes = await request.post('/accounts', {
  477 |       data: { name: 'Account To Delete' },
  478 |       headers: auth(tok),
  479 |     });
  480 |     const account = await createRes.json();
  481 | 
  482 |     await reloadDashboard(page);
  483 |     await page.getByRole('button', { name: 'Accounts' }).click();
  484 |     await expect(page.getByRole('cell', { name: 'Account To Delete' })).toBeVisible({ timeout: 8_000 });
  485 |     await page.getByRole('button', { name: 'Account To Delete' }).first().click();
  486 |     await expect(page.getByRole('heading', { name: 'Account To Delete' })).toBeVisible({ timeout: 5_000 });
  487 | 
  488 |     // window.confirm dialog
  489 |     page.once('dialog', (d) => void d.accept());
  490 |     await page.getByRole('button', { name: 'Delete' }).click();
  491 | 
  492 |     // Returns to accounts list after deletion
  493 |     await expect(page.getByRole('button', { name: 'New Account' })).toBeVisible({ timeout: 8_000 });
  494 |     await expect(page.getByRole('cell', { name: 'Account To Delete' })).not.toBeVisible();
  495 | 
  496 |     // Verify via API
  497 |     const goneRes = await request.get(`/accounts/${account.id}`, { headers: auth(tok) });
  498 |     expect(goneRes.status()).toBe(404);
  499 |   });
  500 | });
  501 | 
  502 | // ── 7. Activities CRUD (API-only — no Activities tab in current SPA) ──────────
  503 | 
  504 | test.describe('Activities CRUD', () => {
  505 |   test('full CRUD lifecycle via REST API', async ({ page, request }) => {
  506 |     await loginAndWait(page);
  507 |     const tok = await bearerToken(page);
  508 | 
  509 |     const cRes = await request.post('/contacts', {
  510 |       data: { name: 'Activity Test Contact' },
  511 |       headers: auth(tok),
  512 |     });
  513 |     const contact = await cRes.json();
  514 | 
  515 |     try {
  516 |       // CREATE
  517 |       const createRes = await request.post('/activities', {
  518 |         data: { title: 'Smoke Call', type: 'call', contact_id: contact.id, body: 'Initial note' },
  519 |         headers: auth(tok),
  520 |       });
  521 |       expect(createRes.ok()).toBeTruthy();
  522 |       const activity = await createRes.json();
  523 |       expect(activity.title).toBe('Smoke Call');
  524 |       expect(activity.type).toBe('call');
  525 | 
  526 |       // LIST
  527 |       const listRes = await request.get('/activities', { headers: auth(tok) });
  528 |       expect(listRes.ok()).toBeTruthy();
  529 |       const list: { id: number }[] = await listRes.json();
  530 |       expect(list.some((a) => a.id === activity.id)).toBeTruthy();
  531 | 
  532 |       // GET by ID
  533 |       const getRes = await request.get(`/activities/${activity.id}`, { headers: auth(tok) });
  534 |       expect(getRes.ok()).toBeTruthy();
  535 |       expect((await getRes.json()).id).toBe(activity.id);
  536 | 
  537 |       // PATCH
  538 |       const patchRes = await request.patch(`/activities/${activity.id}`, {
  539 |         data: { body: 'Updated note' },
  540 |         headers: auth(tok),
  541 |       });
  542 |       expect(patchRes.ok()).toBeTruthy();
  543 |       expect((await patchRes.json()).body).toBe('Updated note');
  544 | 
  545 |       // DELETE
  546 |       const delRes = await request.delete(`/activities/${activity.id}`, { headers: auth(tok) });
  547 |       expect(delRes.ok()).toBeTruthy();
  548 | 
  549 |       // 404 after deletion
  550 |       const goneRes = await request.get(`/activities/${activity.id}`, { headers: auth(tok) });
  551 |       expect(goneRes.status()).toBe(404);
  552 |     } finally {
  553 |       await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
  554 |     }
  555 |   });
  556 | 
  557 |   test('Activities navigation tab [UI gap — no Activities tab in current SPA]', async ({ page }) => {
  558 |     await loginAndWait(page);
  559 |     // Expected to FAIL: the SPA has no Activities tab — defect marker
> 560 |     await expect(page.getByRole('button', { name: 'Activities' })).toBeVisible({ timeout: 3_000 });
      |                                                                    ^ Error: expect(locator).toBeVisible() failed
  561 |   });
  562 | });
  563 | 
  564 | // ── 8. Import flow ────────────────────────────────────────────────────────────
  565 | 
  566 | test.describe('Import', () => {
  567 |   test('POST /contacts/import accepts CSV body and returns imported count', async ({
  568 |     page,
  569 |     request,
  570 |   }) => {
  571 |     await loginAndWait(page);
  572 |     const tok = await bearerToken(page);
  573 | 
  574 |     const csv = [
  575 |       'name,email,phone,company',
  576 |       'Import Alpha,alpha.imp@test.internal,555-1001,Alpha Inc',
  577 |       'Import Beta,beta.imp@test.internal,555-1002,Beta Inc',
  578 |     ].join('\n');
  579 | 
  580 |     const res = await request.post('/contacts/import', {
  581 |       data: { csv },
  582 |       headers: auth(tok),
  583 |     });
  584 |     expect(res.ok()).toBeTruthy();
  585 |     const body = await res.json();
  586 |     expect(body.imported).toBe(2);
  587 |     expect(body.errors).toHaveLength(0);
  588 | 
  589 |     // Cleanup imported contacts
  590 |     const contacts: { id: number; name: string }[] = await (
  591 |       await request.get('/contacts', { headers: auth(tok) })
  592 |     ).json();
  593 |     for (const name of ['Import Alpha', 'Import Beta']) {
  594 |       const c = contacts.find((x) => x.name === name);
  595 |       if (c) await request.delete(`/contacts/${c.id}`, { headers: auth(tok) });
  596 |     }
  597 |   });
  598 | 
  599 |   test('import UI trigger [UI gap — no import button in current SPA]', async ({ page }) => {
  600 |     await loginAndWait(page);
  601 |     // Expected to FAIL: the SPA has no import button/modal — defect marker
  602 |     const trigger = page
  603 |       .getByRole('button', { name: /import/i })
  604 |       .or(page.getByRole('link', { name: /import/i }));
  605 |     await expect(trigger).toBeVisible({ timeout: 3_000 });
  606 |   });
  607 | });
  608 | 
  609 | // ── 9. Export flow ────────────────────────────────────────────────────────────
  610 | 
  611 | test.describe('Export', () => {
  612 |   test('GET /contacts/export returns text/csv with expected column headers', async ({
  613 |     page,
  614 |     request,
  615 |   }) => {
  616 |     await loginAndWait(page);
  617 |     const tok = await bearerToken(page);
  618 | 
  619 |     const res = await request.get('/contacts/export', { headers: auth(tok) });
  620 |     expect(res.ok()).toBeTruthy();
  621 |     expect(res.headers()['content-type']).toContain('text/csv');
  622 |     const csv = await res.text();
  623 |     // Verify the CSV header row contains expected columns
  624 |     expect(csv).toContain('name');
  625 |     expect(csv).toContain('email');
  626 |     expect(csv).toContain('id');
  627 |   });
  628 | 
  629 |   test('export UI trigger [UI gap — no export button in current SPA]', async ({ page }) => {
  630 |     await loginAndWait(page);
  631 |     // Expected to FAIL: the SPA has no export button — defect marker
  632 |     const trigger = page
  633 |       .getByRole('button', { name: /export/i })
  634 |       .or(page.getByRole('link', { name: /export/i }));
  635 |     await expect(trigger).toBeVisible({ timeout: 3_000 });
  636 |   });
  637 | });
  638 | 
```