# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: smoke.spec.ts >> Deals CRUD >> deal detail/edit UI [UI gap — no per-deal detail page in SPA]
- Location: e2e/smoke.spec.ts:310:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('Gap Test Deal')
Expected: visible
Timeout: 8000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 8000ms
  - waiting for getByText('Gap Test Deal')

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
  - text: Weighted Forecast $1,520 open deals by stage probability
```

# Test source

```ts
  228 |       expect((await editRes.json()).company).toBe('Patched Corp');
  229 |     } finally {
  230 |       await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
  231 |     }
  232 |   });
  233 | 
  234 |   test('delete contact via API — DELETE /contacts/:id returns 404 after deletion', async ({
  235 |     page,
  236 |     request,
  237 |   }) => {
  238 |     await loginAndWait(page);
  239 |     const tok = await bearerToken(page);
  240 |     const res = await request.post('/contacts', {
  241 |       data: { name: 'API Delete Contact' },
  242 |       headers: auth(tok),
  243 |     });
  244 |     expect(res.ok()).toBeTruthy();
  245 |     const contact = await res.json();
  246 | 
  247 |     const delRes = await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
  248 |     expect(delRes.ok()).toBeTruthy();
  249 | 
  250 |     const goneRes = await request.get(`/contacts/${contact.id}`, { headers: auth(tok) });
  251 |     expect(goneRes.status()).toBe(404);
  252 |   });
  253 | });
  254 | 
  255 | // ── 5. Deals CRUD ─────────────────────────────────────────────────────────────
  256 | 
  257 | test.describe('Deals CRUD', () => {
  258 |   test('create deal via New Deal modal — card appears in kanban board', async ({ page, request }) => {
  259 |     await loginAndWait(page);
  260 |     const tok = await bearerToken(page);
  261 | 
  262 |     // Use a unique name per run so stale data from prior runs never causes strict-mode
  263 |     // violations when we wait for the contact cell to appear.
  264 |     const runTag = Date.now().toString(36).slice(-5);
  265 |     const contactName = `Deal Modal Contact ${runTag}`;
  266 |     const dealTitle = `Smoke Kanban Deal ${runTag}`;
  267 | 
  268 |     // Create a contact so the deal modal dropdown has an option
  269 |     const contactRes = await request.post('/contacts', {
  270 |       data: { name: contactName },
  271 |       headers: auth(tok),
  272 |     });
  273 |     expect(contactRes.ok()).toBeTruthy();
  274 |     const contact = await contactRes.json();
  275 | 
  276 |     try {
  277 |       // Reload so the React state picks up the newly created contact.
  278 |       // Then visit the Contacts tab and wait for the contact row to appear —
  279 |       // this confirms refreshCore() has finished and the contact is in state
  280 |       // before we try to select it in the Deal modal dropdown.
  281 |       await reloadDashboard(page);
  282 |       await page.getByRole('button', { name: 'Contacts' }).click();
  283 |       await expect(page.getByRole('cell', { name: contactName })).toBeVisible({
  284 |         timeout: 10_000,
  285 |       });
  286 |       await page.getByRole('button', { name: 'Pipeline' }).click();
  287 | 
  288 |       await page.getByRole('button', { name: 'New Deal' }).first().click();
  289 |       await expect(page.getByRole('heading', { name: 'New Deal' })).toBeVisible();
  290 | 
  291 |       await page.getByLabel('Title').fill(dealTitle);
  292 |       await page.getByLabel('Contact').selectOption({ label: contactName });
  293 |       await page.getByLabel('Value').fill('5000');
  294 |       await page.getByRole('button', { name: 'Create' }).click();
  295 | 
  296 |       // Bug: newly-created deals have stage_id=null so they never match any kanban column.
  297 |       // This assertion FAILS as a defect marker for the missing stage_id assignment on POST /deals.
  298 |       await expect(page.getByText(dealTitle)).toBeVisible({ timeout: 8_000 });
  299 |     } finally {
  300 |       // Cleanup runs even if the kanban assertion above fails
  301 |       const deals: { id: number; title: string }[] = await (
  302 |         await request.get('/deals', { headers: auth(tok) })
  303 |       ).json();
  304 |       const deal = deals.find((d) => d.title === dealTitle);
  305 |       if (deal) await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
  306 |       await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
  307 |     }
  308 |   });
  309 | 
  310 |   test('deal detail/edit UI [UI gap — no per-deal detail page in SPA]', async ({ page, request }) => {
  311 |     await loginAndWait(page);
  312 |     const tok = await bearerToken(page);
  313 | 
  314 |     const cRes = await request.post('/contacts', {
  315 |       data: { name: 'Deal Gap Contact' },
  316 |       headers: auth(tok),
  317 |     });
  318 |     const contact = await cRes.json();
  319 |     const dRes = await request.post('/deals', {
  320 |       data: { title: 'Gap Test Deal', contact_id: contact.id, value: 100 },
  321 |       headers: auth(tok),
  322 |     });
  323 |     const deal = await dRes.json();
  324 | 
  325 |     try {
  326 |       await reloadDashboard(page);
  327 |       await page.getByRole('button', { name: 'Pipeline' }).click();
> 328 |       await expect(page.getByText('Gap Test Deal')).toBeVisible({ timeout: 8_000 });
      |                                                     ^ Error: expect(locator).toBeVisible() failed
  329 | 
  330 |       // Clicking the deal card should open a detail view — no such UI exists.
  331 |       // This test FAILS as a defect marker for the missing deal-detail page.
  332 |       await page.getByText('Gap Test Deal').first().click();
  333 |       await expect(page.getByRole('heading', { name: /Gap Test Deal/i })).toBeVisible({
  334 |         timeout: 3_000,
  335 |       });
  336 |     } finally {
  337 |       await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
  338 |       await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
  339 |     }
  340 |   });
  341 | 
  342 |   test('edit deal via API — PATCH /deals/:id', async ({ page, request }) => {
  343 |     await loginAndWait(page);
  344 |     const tok = await bearerToken(page);
  345 | 
  346 |     const cRes = await request.post('/contacts', { data: { name: 'Deal Edit Contact' }, headers: auth(tok) });
  347 |     const contact = await cRes.json();
  348 |     const dRes = await request.post('/deals', {
  349 |       data: { title: 'API Edit Deal', contact_id: contact.id, value: 100 },
  350 |       headers: auth(tok),
  351 |     });
  352 |     expect(dRes.ok()).toBeTruthy();
  353 |     const deal = await dRes.json();
  354 | 
  355 |     try {
  356 |       const editRes = await request.patch(`/deals/${deal.id}`, {
  357 |         data: { value: 9999 },
  358 |         headers: auth(tok),
  359 |       });
  360 |       expect(editRes.ok()).toBeTruthy();
  361 |       expect(Number((await editRes.json()).value)).toBe(9999);
  362 |     } finally {
  363 |       await request.delete(`/deals/${deal.id}`, { headers: auth(tok) });
  364 |       await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
  365 |     }
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
```