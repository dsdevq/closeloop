# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: smoke.spec.ts >> Accounts CRUD >> edit account [UI gap — no edit form in account detail view]
- Location: e2e/smoke.spec.ts:450:3

# Error details

```
TimeoutError: locator.click: Timeout 3000ms exceeded.
Call log:
  - waiting for getByRole('button', { name: /edit/i })

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e5]:
      - generic [ref=e6]:
        - img [ref=e8]
        - generic [ref=e13]: CloseLoop CRM
      - navigation [ref=e14]:
        - button "Pipeline" [ref=e15] [cursor=pointer]:
          - img [ref=e16]
          - text: Pipeline
        - button "Contacts" [ref=e18] [cursor=pointer]:
          - img [ref=e19]
          - text: Contacts
        - button "Accounts" [ref=e23] [cursor=pointer]:
          - img [ref=e24]
          - text: Accounts
        - button "Today" [ref=e28] [cursor=pointer]:
          - img [ref=e29]
          - text: Today
        - button "Stats" [ref=e32] [cursor=pointer]:
          - img [ref=e33]
          - text: Stats
      - generic [ref=e35]:
        - generic [ref=e36]:
          - img [ref=e37]
          - generic [ref=e40]: Admin
          - generic [ref=e41]: admin
        - button "Sign out" [ref=e42] [cursor=pointer]:
          - img [ref=e43]
  - main [ref=e46]:
    - generic [ref=e47]:
      - heading "Edit Gap Account" [level=1] [ref=e48]
      - generic [ref=e49]:
        - button "Back" [ref=e50] [cursor=pointer]:
          - img [ref=e51]
          - text: Back
        - button "Delete" [ref=e53] [cursor=pointer]:
          - img [ref=e54]
          - text: Delete
    - generic [ref=e57]:
      - generic [ref=e58]:
        - generic [ref=e59]: Domain
        - generic [ref=e60]: Not set
      - generic [ref=e61]:
        - generic [ref=e62]: Industry
        - generic [ref=e63]: Not set
      - generic [ref=e64]:
        - generic [ref=e65]: Website
        - generic [ref=e66]: Not set
      - generic [ref=e67]:
        - generic [ref=e68]: Phone
        - generic [ref=e69]: Not set
      - generic [ref=e70]:
        - generic [ref=e71]: Address
        - generic [ref=e72]: Not set
    - heading "Linked Contacts" [level=2] [ref=e73]
    - table [ref=e75]:
      - rowgroup [ref=e76]:
        - row "Name Email Phone Company" [ref=e77]:
          - columnheader "Name" [ref=e78]
          - columnheader "Email" [ref=e79]
          - columnheader "Phone" [ref=e80]
          - columnheader "Company" [ref=e81]
      - rowgroup [ref=e82]:
        - row "No linked contacts." [ref=e83]:
          - cell "No linked contacts." [ref=e84]
```

# Test source

```ts
  366 |   });
  367 | 
  368 |   test('delete deal via API — DELETE /deals/:id returns 404 after deletion', async ({
  369 |     page,
  370 |     request,
  371 |   }) => {
  372 |     await loginAndWait(page);
  373 |     const tok = await bearerToken(page);
  374 | 
  375 |     const cRes = await request.post('/contacts', { data: { name: 'Deal Del Contact' }, headers: auth(tok) });
  376 |     const contact = await cRes.json();
  377 |     const dRes = await request.post('/deals', {
  378 |       data: { title: 'API Delete Deal', contact_id: contact.id, value: 1 },
  379 |       headers: auth(tok),
  380 |     });
  381 |     expect(dRes.ok()).toBeTruthy();
  382 |     const deal = await dRes.json();
  383 | 
  384 |     try {
  385 |       const delRes = await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
  386 |       expect(delRes.ok()).toBeTruthy();
  387 | 
  388 |       const goneRes = await request.get(`/deals/${deal.id}`, { headers: auth(tok) });
  389 |       expect(goneRes.status()).toBe(404);
  390 |     } finally {
  391 |       await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
  392 |     }
  393 |   });
  394 | });
  395 | 
  396 | // ── 6. Accounts CRUD ──────────────────────────────────────────────────────────
  397 | 
  398 | test.describe('Accounts CRUD', () => {
  399 |   test('create account via New Account modal — appears in accounts list', async ({ page, request }) => {
  400 |     await loginAndWait(page);
  401 |     await page.getByRole('button', { name: 'Accounts' }).click();
  402 |     await page.getByRole('button', { name: 'New Account' }).click();
  403 | 
  404 |     await expect(page.getByRole('heading', { name: 'New Account' })).toBeVisible();
  405 |     await page.getByLabel('Name').fill('Smoke Account Corp');
  406 |     await page.getByLabel('Domain').fill('smoke.example.com');
  407 |     await page.getByLabel('Industry').fill('Technology');
  408 |     await page.getByRole('button', { name: 'Create' }).click();
  409 | 
  410 |     await expect(page.getByRole('cell', { name: 'Smoke Account Corp' })).toBeVisible({ timeout: 8_000 });
  411 | 
  412 |     // Cleanup
  413 |     const tok = await bearerToken(page);
  414 |     const list: { id: number; name: string }[] = await (
  415 |       await request.get('/accounts', { headers: auth(tok) })
  416 |     ).json();
  417 |     const acc = list.find((a) => a.name === 'Smoke Account Corp');
  418 |     if (acc) await request.delete(`/accounts/${acc.id}`, { headers: auth(tok) });
  419 |   });
  420 | 
  421 |   test('open account detail view — shows domain and linked contacts section', async ({
  422 |     page,
  423 |     request,
  424 |   }) => {
  425 |     await loginAndWait(page);
  426 |     const tok = await bearerToken(page);
  427 |     const createRes = await request.post('/accounts', {
  428 |       data: { name: 'Detail Account', domain: 'detail.example.com', industry: 'Finance' },
  429 |       headers: auth(tok),
  430 |     });
  431 |     const account = await createRes.json();
  432 | 
  433 |     try {
  434 |       await reloadDashboard(page);
  435 |       await page.getByRole('button', { name: 'Accounts' }).click();
  436 |       await expect(page.getByRole('cell', { name: 'Detail Account' })).toBeVisible({ timeout: 8_000 });
  437 | 
  438 |       // Click the account name button in the table row to open the detail view
  439 |       await page.getByRole('button', { name: 'Detail Account' }).first().click();
  440 | 
  441 |       await expect(page.getByRole('heading', { name: 'Detail Account' })).toBeVisible({ timeout: 5_000 });
  442 |       await expect(page.getByText('Domain')).toBeVisible();
  443 |       await expect(page.getByText('detail.example.com')).toBeVisible();
  444 |       await expect(page.getByRole('heading', { name: 'Linked Contacts' })).toBeVisible();
  445 |     } finally {
  446 |       await request.delete(`/accounts/${account.id}`, { headers: auth(tok) });
  447 |     }
  448 |   });
  449 | 
  450 |   test('edit account [UI gap — no edit form in account detail view]', async ({ page, request }) => {
  451 |     await loginAndWait(page);
  452 |     const tok = await bearerToken(page);
  453 |     const createRes = await request.post('/accounts', {
  454 |       data: { name: 'Edit Gap Account' },
  455 |       headers: auth(tok),
  456 |     });
  457 |     const account = await createRes.json();
  458 | 
  459 |     try {
  460 |       await reloadDashboard(page);
  461 |       await page.getByRole('button', { name: 'Accounts' }).click();
  462 |       await page.getByRole('button', { name: 'Edit Gap Account' }).first().click();
  463 |       await expect(page.getByRole('heading', { name: 'Edit Gap Account' })).toBeVisible({ timeout: 5_000 });
  464 | 
  465 |       // No edit form/button exists in the account detail view — defect marker
> 466 |       await page.getByRole('button', { name: /edit/i }).click({ timeout: 3_000 });
      |                                                         ^ TimeoutError: locator.click: Timeout 3000ms exceeded.
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
  560 |     await expect(page.getByRole('button', { name: 'Activities' })).toBeVisible({ timeout: 3_000 });
  561 |   });
  562 | });
  563 | 
  564 | // ── 8. Import flow ────────────────────────────────────────────────────────────
  565 | 
  566 | test.describe('Import', () => {
```