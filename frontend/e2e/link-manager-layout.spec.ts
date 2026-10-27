import { expect, test, type Page } from '@playwright/test';

const project = { id: 1, name: 'Java Maven – Architecture and integration reference project', status: 'completed' };
const codeA = { type: 'entity', title: 'OrderController', code_ref: { file_path: 'src/OrderController.java', line: 10, source_id: 7 } };
const codeB = { type: 'entity', title: 'OrderService', code_ref: { file_path: 'src/OrderService.java', line: 20, source_id: 7 } };
const docA = { type: 'document', title: 'Architecture guide', source_type: 'Local', doc_source_id: 9 };
const docB = { type: 'document', title: 'Operations handbook', source_type: 'Local', doc_source_id: 9 };
const links = [[codeA, codeB], [docA, codeB], [docA, docB]].map(([source_a, source_b], index) => ({
  id: index + 1, source_a, source_b, score: 1, status: 'pending', created_by: 'auto',
  context: 'Verified relation with original source references.', link_type: 'semantic',
}));

async function openManager(page: Page, baseURL: string, views: number, split = 50) {
  const configs = ['linkmanager', 'chat', 'graph', 'code'].slice(0, views);
  const session = { id: 9001, uuid: 'link-layout', title: 'Link layout audit', project_id: 1,
    snapshot_json: { panelConfigs: configs, panelFrozen: configs.map(() => false), selectedProjectId: 1,
      splitPercent: split, panelSelections: configs.map(() => ({ selectedFile: null, selectedEntity: null, selectedDoc: null })) } };
  const origin = new URL(baseURL).origin;
  const posts: string[] = [];
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin === origin) return route.continue();
    if (route.request().method() === 'POST') posts.push(url.pathname);
    let body: unknown = [];
    if (url.pathname === '/auth/me') body = { id: 1, username: 'layout-audit', is_admin: true };
    else if (url.pathname === '/projects') body = [project];
    else if (url.pathname === '/chat/sessions/page') body = { sessions: [session], has_more: false, limit: 30 };
    else if (url.pathname.startsWith('/chat/sessions/by-uuid/')) body = session;
    else if (url.pathname === '/ai-profiles') body = { active_profile_id: 1, profiles: [{ id: 1, name: 'Internal Qwen', llm_model: 'qwen3:32b', provider: 'ollama' }] };
    else if (url.pathname === '/embedding-profiles') body = { profiles: [] };
    else if (url.pathname.endsWith('/knowledge-sources')) body = [
      { id: 7, project_id: 1, name: 'Java sources – modules and generated interfaces', type: 'Git' },
      { id: 9, project_id: 1, name: 'Architecture and operations documentation', type: 'Local' },
    ];
    else if (url.pathname.endsWith('/content')) body = { content: `Content of ${url.searchParams.get('path')}`, format: 'text' };
    else if (url.pathname.endsWith('/link-recommendations/estimate')) body = { entities_to_scan: 12, estimated_llm_reviews_max: 12, estimated_embedding_calls_max: 12 };
    else if (url.pathname === '/knowledge-links/estimate') body = { chunk_count: 4, estimated_llm_reviews_max: 20 };
    else if (url.pathname.endsWith('/compute')) body = { run_id: 100, started: true };
    else if (url.pathname.endsWith('/link-recommendations')) body = { links: [], counts: { pending: 0, approved: 0, rejected: 0 } };
    else if (url.pathname === '/knowledge-links/counts') body = { pending: 3, approved: 0, rejected: 0 };
    else if (url.pathname === '/knowledge-links') body = links;
    else if (url.pathname === '/graph') body = { nodes: [], edges: [] };
    else if (url.pathname === '/model-info') body = { llm: 'audit', embedding: 'audit' };
    else if (url.pathname === '/models') body = { models: [] };
    else if (url.pathname === '/jobs') body = { jobs: [] };
    await route.fulfill({ status: 200, headers: { 'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*' }, body: JSON.stringify(body) });
  });
  await page.goto(baseURL);
  await page.locator('#project-selector').click();
  await page.getByRole('option', { name: project.name }).click();
  await page.getByText(session.title, { exact: true }).first().click();
  const view = page.getByTestId('link-manager-view');
  await expect(view).toBeVisible();
  return { view, posts };
}

const layouts = [
  { width: 1440, height: 900, views: 1 },
  { width: 1440, height: 900, views: 2 },
  { width: 1440, height: 900, views: 3 },
  { width: 1440, height: 900, views: 4 },
  { width: 1280, height: 800, views: 3 },
  { width: 1280, height: 800, views: 4 },
  { width: 1920, height: 1080, views: 3 },
  { width: 1440, height: 900, views: 2, split: 25 },
];

for (const layout of layouts) {
  test(`link controls fit ${layout.width}x${layout.height}, ${layout.views} panels, split ${layout.split ?? 50}`, async ({ page, baseURL }) => {
    await page.setViewportSize(layout);
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const { view, posts } = await openManager(page, baseURL!, layout.views, layout.split);
    for (const id of ['link-manager-toolbar', 'link-manager-filters']) {
      await expect.poll(() => view.getByTestId(id).evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1);
    }
    const kind = view.getByRole('combobox', { name: 'Beziehungsart' });
    if (await kind.isVisible()) await kind.selectOption('codeCode');
    else await view.getByRole('button', { name: 'Code ↔ Code', exact: true }).click();
    await expect(view.getByText('OrderController', { exact: true })).toBeVisible();
    await expect(view.getByText('Architecture guide', { exact: true })).toHaveCount(0);

    const trigger = view.getByRole('button', { name: 'Analyse starten', exact: true });
    await trigger.click();
    const dialog = page.getByRole('dialog', { name: 'Analyse konfigurieren' });
    await expect(dialog).toBeVisible();
    expect(posts.filter(path => path.endsWith('/compute'))).toHaveLength(0);
    await dialog.getByLabel('Mindest-Wahrscheinlichkeit', { exact: true }).fill('70');
    await dialog.getByText('Erweitert', { exact: true }).click();
    await dialog.getByLabel('Parallele Bewertungen', { exact: true }).fill('2');
    await expect.poll(() => dialog.evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1);
    const bounds = (await dialog.boundingBox())!;
    expect(bounds.x).toBeGreaterThanOrEqual(20);
    expect(bounds.y).toBeGreaterThanOrEqual(20);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(layout.width - 20);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(layout.height - 20);
    if (process.env.LINK_LAYOUT_SCREENSHOTS) await page.screenshot({ path: `${process.env.LINK_LAYOUT_SCREENSHOTS}/${layout.width}-${layout.views}-dialog.png` });
    await dialog.getByRole('button', { name: 'Abbrechen', exact: true }).press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
    await trigger.click();
    await expect(dialog.getByLabel('Mindest-Wahrscheinlichkeit', { exact: true })).toHaveValue('70');
    await dialog.getByRole('button', { name: 'Abbrechen', exact: true }).click();
    expect(errors).toEqual([]);
    if (process.env.LINK_LAYOUT_SCREENSHOTS) await page.screenshot({ path: `${process.env.LINK_LAYOUT_SCREENSHOTS}/${layout.width}-${layout.views}-${layout.split ?? 50}.png` });
  });
}

test('analysis starts only after settings and workload confirmation; dialog survives a resize', async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const { view, posts } = await openManager(page, baseURL!, 3);
  await view.getByRole('button', { name: 'Analyse starten' }).click();
  const dialog = page.getByRole('dialog', { name: 'Analyse konfigurieren' });
  await dialog.getByLabel('Mindest-Wahrscheinlichkeit', { exact: true }).fill('75');
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(dialog.getByLabel('Mindest-Wahrscheinlichkeit', { exact: true })).toHaveValue('75');
  const dismissed = new Promise<void>(resolve => page.once('dialog', async confirm => { await confirm.dismiss(); resolve(); }));
  await dialog.getByRole('button', { name: 'Analyse starten', exact: true }).click();
  await dismissed;
  await expect(dialog.getByRole('button', { name: 'Analyse starten', exact: true })).toBeEnabled();
  await expect(dialog).toBeVisible();
  expect(posts.filter(path => path.endsWith('/compute'))).toHaveLength(0);
  page.once('dialog', confirm => confirm.accept());
  const started = page.waitForRequest(request => request.url().includes('/link-recommendations/compute') && request.method() === 'POST');
  await dialog.getByRole('button', { name: 'Analyse starten', exact: true }).click();
  expect(new URL((await started).url()).searchParams.get('min_confidence')).toBe('75');
  await expect(dialog).toBeHidden();
});

test('dialog remains usable with enlarged desktop text, light theme, English and keyboard navigation', async ({ page, baseURL }) => {
  await page.addInitScript(() => {
    localStorage.setItem('doctus-language', 'en');
    localStorage.setItem('doctus-theme', 'light');
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  const { view, posts } = await openManager(page, baseURL!, 4);
  await page.evaluate(() => { document.documentElement.style.fontSize = '20px'; });
  const trigger = view.getByRole('button', { name: 'Start analysis', exact: true });
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: 'Configure analysis' });
  await expect(dialog).toBeVisible();
  const model = dialog.getByRole('combobox');
  await model.click();
  await page.getByRole('option', { name: /Internal Qwen/ }).press('Escape');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Start analysis', exact: true }).focus();
  await page.keyboard.press('Tab');
  await expect(dialog.getByRole('button', { name: 'Close dialog', exact: true })).toBeFocused();
  await expect.poll(() => dialog.evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1);
  if (process.env.LINK_LAYOUT_SCREENSHOTS) await page.screenshot({ path: `${process.env.LINK_LAYOUT_SCREENSHOTS}/english-light-large-text.png` });
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
  expect(posts.filter(path => path.endsWith('/compute'))).toHaveLength(0);
});

test('opens both sides of a document relationship in independent panels', async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const { view } = await openManager(page, baseURL!, 2);
  const kind = view.getByRole('combobox', { name: 'Beziehungsart' });
  if (await kind.isVisible()) await kind.selectOption('docDoc');
  else await view.getByRole('button', { name: 'Doc ↔ Doc', exact: true }).click();
  const buttons = view.getByTitle('Doku-Seite öffnen');
  await expect(buttons).toHaveCount(2);
  await buttons.nth(0).click();
  await expect(page.locator('[title="Architecture guide"]').last()).toBeVisible();
  await buttons.nth(1).click();
  await expect(page.locator('[title="Architecture guide"]').last()).toBeVisible();
  await expect(page.locator('[title="Operations handbook"]').last()).toBeVisible();
  await expect(page.getByText('Content of Architecture guide')).toBeVisible();
  await expect(page.getByText('Content of Operations handbook')).toBeVisible();
  await buttons.nth(0).click();
  await expect(page.locator('[title="Architecture guide"]')).toHaveCount(1);
  await expect(page.locator('[title="Operations handbook"]')).toHaveCount(1);
  await expect(view).toBeVisible();
});
