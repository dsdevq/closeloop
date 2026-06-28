# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: smoke.spec.ts >> Contacts CRUD >> contact detail/edit UI [UI gap — no per-contact detail page exists in SPA]
- Location: e2e/smoke.spec.ts:182:3

# Error details

```
TimeoutError: locator.click: Timeout 3000ms exceeded.
Call log:
  - waiting for getByRole('row').filter({ hasText: 'Gap Test Contact' }).getByRole('button').or(getByRole('row').filter({ hasText: 'Gap Test Contact' }).getByRole('link')).first()

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
        - button "Contacts" [active] [ref=e18] [cursor=pointer]:
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
      - heading "Contacts" [level=1] [ref=e48]
      - button "New Contact" [ref=e49] [cursor=pointer]:
        - img [ref=e50]
        - text: New Contact
    - generic [ref=e51]:
      - generic [ref=e52]:
        - img [ref=e53]
        - text: Saved Views
      - generic [ref=e56]: No saved views
    - table [ref=e58]:
      - rowgroup [ref=e59]:
        - row "Name Email Phone Company Account Lead Score" [ref=e60]:
          - columnheader "Name" [ref=e61]
          - columnheader "Email" [ref=e62]
          - columnheader "Phone" [ref=e63]
          - columnheader "Company" [ref=e64]
          - columnheader "Account" [ref=e65]
          - columnheader "Lead Score" [ref=e66]
      - rowgroup [ref=e67]:
        - row "Deal Modal Contact 0.0" [ref=e68]:
          - cell "Deal Modal Contact" [ref=e69]
          - cell [ref=e70]
          - cell [ref=e71]
          - cell [ref=e72]
          - cell [ref=e73]
          - cell "0.0" [ref=e74]
        - row "Deal Modal Contact pw311 0.0" [ref=e75]:
          - cell "Deal Modal Contact pw311" [ref=e76]
          - cell [ref=e77]
          - cell [ref=e78]
          - cell [ref=e79]
          - cell [ref=e80]
          - cell "0.0" [ref=e81]
        - row "Test 0.0" [ref=e82]:
          - cell "Test" [ref=e83]
          - cell [ref=e84]
          - cell [ref=e85]
          - cell [ref=e86]
          - cell [ref=e87]
          - cell "0.0" [ref=e88]
        - row "Gap Test Contact 0.0" [ref=e89]:
          - cell "Gap Test Contact" [ref=e90]
          - cell [ref=e91]
          - cell [ref=e92]
          - cell [ref=e93]
          - cell [ref=e94]
          - cell "0.0" [ref=e95]
```

# Test source

```ts
  103 | 
  104 |   test('valid credentials show dashboard nav tabs', async ({ page }) => {
  105 |     await login(page);
  106 |     await expect(page.getByRole('button', { name: 'Pipeline' })).toBeVisible({ timeout: 15_000 });
  107 |     await expect(page.getByRole('button', { name: 'Contacts' })).toBeVisible();
  108 |     await expect(page.getByRole('button', { name: 'Accounts' })).toBeVisible();
  109 |     await expect(page.getByRole('button', { name: 'Today' })).toBeVisible();
  110 |     await expect(page.getByRole('button', { name: 'Stats' })).toBeVisible();
  111 |   });
  112 | 
  113 |   test('invalid credentials display an error message', async ({ page }) => {
  114 |     await page.goto('/login.html');
  115 |     await page.getByLabel('Email').fill('nobody@nowhere.invalid');
  116 |     await page.getByLabel('Password').fill('definitelywrong');
  117 |     await page.getByRole('button', { name: 'Sign in' }).click();
  118 |     // The LoginView renders <div className="... text-red-700">{error}</div>
  119 |     await expect(page.locator('.text-red-700')).toBeVisible({ timeout: 8_000 });
  120 |   });
  121 | 
  122 |   test('unauthenticated visit to / shows login form (SPA client-side guard)', async ({ page }) => {
  123 |     await page.goto('/');
  124 |     // Wipe stored tokens so the React app reverts to LoginView on next render
  125 |     await page.evaluate(() => {
  126 |       localStorage.removeItem('access_token');
  127 |       localStorage.removeItem('refresh_token');
  128 |       localStorage.removeItem('current_user');
  129 |     });
  130 |     await page.reload();
  131 |     await expect(page.getByLabel('Email')).toBeVisible({ timeout: 8_000 });
  132 |     await expect(page.getByRole('button', { name: 'Pipeline' })).not.toBeVisible();
  133 |   });
  134 | });
  135 | 
  136 | // ── 3. Navigation ─────────────────────────────────────────────────────────────
  137 | 
  138 | test.describe('Navigation', () => {
  139 |   test.beforeEach(async ({ page }) => {
  140 |     await loginAndWait(page);
  141 |   });
  142 | 
  143 |   const NAV_TABS = ['Pipeline', 'Contacts', 'Accounts', 'Today', 'Stats'] as const;
  144 | 
  145 |   for (const tab of NAV_TABS) {
  146 |     test(`"${tab}" tab is clickable and renders non-blank content`, async ({ page }) => {
  147 |       await page.getByRole('button', { name: tab }).click();
  148 |       const main = page.locator('main');
  149 |       await expect(main).toBeVisible();
  150 |       const text = await main.textContent();
  151 |       expect((text ?? '').trim().length).toBeGreaterThan(0);
  152 |     });
  153 |   }
  154 | });
  155 | 
  156 | // ── 4. Contacts CRUD ──────────────────────────────────────────────────────────
  157 | 
  158 | test.describe('Contacts CRUD', () => {
  159 |   test('create contact via New Contact modal — appears in contacts table', async ({ page, request }) => {
  160 |     await loginAndWait(page);
  161 |     await page.getByRole('button', { name: 'Contacts' }).click();
  162 |     await page.getByRole('button', { name: 'New Contact' }).click();
  163 | 
  164 |     await expect(page.getByRole('heading', { name: 'New Contact' })).toBeVisible();
  165 |     await page.getByLabel('Name').fill('Smoke UI Contact');
  166 |     await page.getByLabel('Email').fill('smoke.ui@test.internal');
  167 |     await page.getByLabel('Phone').fill('555-0001');
  168 |     await page.getByLabel('Company').fill('Smoke Labs');
  169 |     await page.getByRole('button', { name: 'Create' }).click();
  170 | 
  171 |     await expect(page.getByRole('cell', { name: 'Smoke UI Contact' })).toBeVisible({ timeout: 8_000 });
  172 | 
  173 |     // Cleanup
  174 |     const tok = await bearerToken(page);
  175 |     const list: { id: number; name: string }[] = await (
  176 |       await request.get('/contacts', { headers: auth(tok) })
  177 |     ).json();
  178 |     const c = list.find((x) => x.name === 'Smoke UI Contact');
  179 |     if (c) await request.delete(`/contacts/${c.id}`, { headers: auth(tok) });
  180 |   });
  181 | 
  182 |   test('contact detail/edit UI [UI gap — no per-contact detail page exists in SPA]', async ({
  183 |     page,
  184 |     request,
  185 |   }) => {
  186 |     await loginAndWait(page);
  187 |     const tok = await bearerToken(page);
  188 |     const res = await request.post('/contacts', {
  189 |       data: { name: 'Gap Test Contact' },
  190 |       headers: auth(tok),
  191 |     });
  192 |     const contact = await res.json();
  193 | 
  194 |     try {
  195 |       await reloadDashboard(page);
  196 |       await page.getByRole('button', { name: 'Contacts' }).click();
  197 |       await expect(page.getByRole('cell', { name: 'Gap Test Contact' })).toBeVisible({ timeout: 8_000 });
  198 | 
  199 |       // The contacts table has NO clickable link/button per row beyond the Account link.
  200 |       // Attempting to navigate to a detail page will FAIL — defect marker.
  201 |       const row = page.getByRole('row').filter({ hasText: 'Gap Test Contact' });
  202 |       const clickable = row.getByRole('button').or(row.getByRole('link'));
> 203 |       await clickable.first().click({ timeout: 3_000 });
      |                               ^ TimeoutError: locator.click: Timeout 3000ms exceeded.
  204 |       await expect(page.getByRole('heading', { name: /Gap Test Contact/i })).toBeVisible({
  205 |         timeout: 3_000,
  206 |       });
  207 |     } finally {
  208 |       await request.delete(`/contacts/${contact.id}`, { headers: auth(tok) });
  209 |     }
  210 |   });
  211 | 
  212 |   test('edit contact via API — PATCH /contacts/:id', async ({ page, request }) => {
  213 |     await loginAndWait(page);
  214 |     const tok = await bearerToken(page);
  215 |     const res = await request.post('/contacts', {
  216 |       data: { name: 'API Edit Contact', email: 'edit@test.internal' },
  217 |       headers: auth(tok),
  218 |     });
  219 |     expect(res.ok()).toBeTruthy();
  220 |     const contact = await res.json();
  221 | 
  222 |     try {
  223 |       const editRes = await request.patch(`/contacts/${contact.id}`, {
  224 |         data: { company: 'Patched Corp' },
  225 |         headers: auth(tok),
  226 |       });
  227 |       expect(editRes.ok()).toBeTruthy();
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
```