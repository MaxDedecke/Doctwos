import { expect, test, type Page } from '@playwright/test';

// Render the real graph UI with deterministic browser-only API responses.
// No sessions, links or sources are written to the running backend.
const project = { id: 1, name: 'Graph layout audit', status: 'completed', repo_id: 1 };
const documentNode = { id: 'doc:1', type: 'document', label: 'Architecture and integration handbook', url: 'https://audit.invalid/architecture', source_type: 'confluence', source_id: 2, project_id: 1 };
const nodes = [
  documentNode,
  { id: 'entity:1', type: 'entity', label: 'ContentRepositoryEndpoint', entity_type: 'class', file_path: 'src/ContentRepositoryEndpoint.java', source_id: 1 },
  { id: 'file:1', type: 'code_file', label: 'ContentRepositoryEndpoint.java', file_path: 'src/ContentRepositoryEndpoint.java', source_id: 1, entity_ids: [1] },
  { id: 'entity:2', type: 'entity', label: 'Booking processor', entity_type: 'program', file_path: 'src/BOOKING.cbl', source_id: 1 },
  { id: 'doc:2', type: 'document', label: 'Integration guide', source_type: 'pdf', source_id: 2 },
  { id: 'external:1', type: 'external', label: 'Customer database', source_type: 'jira', source_id: 2 },
].map((node, index) => ({ ...node, project_id: 1, fx: Math.cos(index) * 100, fy: Math.sin(index) * 100 }));
const edges = ['semantic', 'keyword', 'documented', 'syntactic', 'coref', 'manual', 'code_dependency'].map((type, index) => ({
  id: `edge:${index}`, source: nodes[index % nodes.length].id, target: nodes[(index + 1) % nodes.length].id,
  link_type: type, direction: ['directed', 'undirected', 'bidirectional'][index % 3], score: 0.9,
}));
const layouts = [
  { width: 1440, height: 900, views: 1, split: 50 },
  { width: 1440, height: 900, views: 2, split: 50 },
  { width: 1440, height: 900, views: 3, split: 50 },
  { width: 1440, height: 900, views: 4, split: 50 },
  { width: 1280, height: 800, views: 3, split: 50 },
  { width: 1280, height: 800, views: 4, split: 50 },
  { width: 1920, height: 1080, views: 3, split: 50 },
  { width: 1440, height: 900, views: 2, split: 25 },
];

async function openGraph(page: Page, baseURL: string, views: number, split: number) {
  const configs = ['graph', 'chat', 'code', 'doc'].slice(0, views);
  const session = {
    id: 9001, uuid: 'graph-layout-audit', title: 'Layout audit session', project_id: 1,
    snapshot_json: {
      panelConfigs: configs, panelFrozen: configs.map(() => false), selectedProjectId: 1, splitPercent: split,
      panelSelections: configs.map(type => ({ selectedFile: null, selectedEntity: null, selectedDoc: type === 'graph' ? { name: documentNode.label, url: documentNode.url, source_id: 2 } : null })),
    },
  };
  const origin = new URL(baseURL).origin;
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin === origin) return route.continue();
    let body: unknown = [];
    if (url.pathname === '/auth/me') body = { id: 1, username: 'layout-audit', is_admin: true };
    else if (url.pathname === '/projects') body = [project];
    else if (url.pathname === '/chat/sessions/page') body = { sessions: [session], has_more: false, limit: 30 };
    else if (url.pathname.startsWith('/chat/sessions/by-uuid/')) body = session;
    else if (url.pathname === '/graph') body = { nodes, edges };
    else if (url.pathname === '/graph/neighborhood') body = { nodes, edges, focus_id: documentNode.id, has_more: true, next_cursor: 'audit-next' };
    else if (url.pathname === '/knowledge-links') body = { id: 42 };
    else if (url.pathname === '/knowledge-sources') body = [
      { id: 1, project_id: 1, name: 'Spring Web Services source code and sample applications', source_type: 'git', sync_status: 'completed' },
      { id: 2, project_id: 1, name: 'Architecture and integration documentation', source_type: 'confluence', sync_status: 'completed' },
    ];
    else if (url.pathname === '/model-info') body = { llm: 'audit', embedding: 'audit' };
    else if (url.pathname === '/models') body = { models: [] };
    else if (url.pathname.endsWith('/stats')) body = { total_files: 3, total_lines: 100, languages: [] };
    await route.fulfill({ status: 200, headers: {
      'Content-Type': 'application/json', 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*',
    }, body: JSON.stringify(body) });
  });
  await page.goto(baseURL);
  await page.locator('#project-selector').click();
  await page.getByRole('option', { name: project.name }).click();
  await page.getByText(session.title, { exact: true }).first().click();
  await expect(page.getByTestId('knowledge-graph-view').locator('canvas').first()).toBeVisible();
  return page.getByTestId('knowledge-graph-view');
}

for (const layout of layouts) {
  test(`graph controls remain usable at ${layout.width}x${layout.height}, ${layout.views} views, split ${layout.split}`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width: layout.width, height: layout.height });
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const graph = await openGraph(page, baseURL!, layout.views, layout.split);
    const toolbar = graph.getByTestId('graph-toolbar');
    await expect.poll(() => toolbar.evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1);
    expect((await graph.locator('canvas').first().boundingBox())!.height).toBeGreaterThan(150);

    const sourceRequest = page.waitForRequest(request => new URL(request.url()).pathname === '/graph' && request.url().includes('focus_source_id=2'));
    await graph.getByRole('combobox', { name: 'Quelle bevorzugen', exact: true }).selectOption('2');
    await sourceRequest;
    await graph.getByRole('button', { name: 'Filter', exact: true }).click();
    const filter = page.getByRole('region', { name: 'Filter', exact: true });
    await filter.getByRole('button', { name: 'semantisch', exact: true }).click();
    await expect(graph.getByRole('button', { name: /Filter.*1 Filter ausgeblendet/ })).toBeVisible();
    await filter.getByRole('button', { name: 'Bereich schließen' }).press('Escape');
    await expect(graph.getByRole('button', { name: /Filter.*1 Filter ausgeblendet/ })).toBeFocused();
    await graph.getByRole('button', { name: /Filter.*1 Filter ausgeblendet/ }).click();
    await filter.getByRole('textbox', { name: 'Filter suchen' }).fill('semantisch');
    await expect(filter.getByRole('button', { name: 'semantisch', exact: true })).toHaveAttribute('aria-pressed', 'false');
    await filter.getByRole('button', { name: 'Alle Typen anzeigen' }).click();
    await filter.getByRole('button', { name: 'Bereich schließen' }).click();

    await graph.getByRole('button', { name: 'Ansicht', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Legende', exact: true }).click();
    const legend = page.getByRole('region', { name: 'Legende', exact: true });
    await expect(legend.getByText('semantisch', { exact: true })).toBeVisible();
    await legend.getByRole('button', { name: 'Bereich schließen' }).press('Escape');
    await expect(graph.getByRole('button', { name: 'Ansicht', exact: true })).toBeFocused();

    const showDetails = graph.getByRole('button', { name: 'Details anzeigen', exact: true });
    if (await showDetails.count()) await showDetails.click();
    const inspector = graph.getByTestId('graph-tool-panel');
    expect((await inspector.getByTestId('graph-tool-panel-body').boundingBox())!.height).toBeGreaterThan(100);
    await inspector.getByRole('button', { name: 'Verknüpfung erstellen', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Verknüpfung erstellen', exact: true });
    await dialog.getByRole('button', { name: 'ContentRepositoryEndpoint', exact: true }).click();
    await dialog.getByLabel('Beschreibung (optional)').fill('Architecture reference');
    await dialog.getByLabel('Richtung (Start → Ziel)').selectOption('directed');
    const createRequest = page.waitForRequest(request => new URL(request.url()).pathname === '/knowledge-links' && request.method() === 'POST');
    await dialog.getByRole('button', { name: 'Verknüpfen', exact: true }).click();
    expect((await createRequest).postDataJSON()).toMatchObject({ direction: 'directed', context: 'Architecture reference' });
    await expect(dialog).toBeHidden();

    await inspector.getByRole('button', { name: 'Nur Nachbarschaft laden', exact: true }).click();
    await expect(graph.getByRole('button', { name: 'Zurück zur Übersicht', exact: true })).toBeVisible();
    await expect.poll(() => toolbar.evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1);
    const loadMore = graph.getByTestId('graph-neighborhood-navigation').getByRole('button', { name: 'Weitere Verbindungen laden', exact: true });
    await loadMore.click();
    await graph.getByRole('button', { name: 'Zurück zur Übersicht', exact: true }).click();
    await expect(loadMore).toBeHidden();
    expect(errors).toEqual([]);
  });
}

test('keeps the canvas and explicit inspector state when resizing and using English at a larger UI scale', async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const graph = await openGraph(page, baseURL!, 1, 50);
  await expect(graph.getByTestId('graph-tool-panel')).toHaveAttribute('data-mode', 'side');
  await graph.locator('canvas').first().evaluate(element => element.setAttribute('data-instance-marker', 'same-graph'));
  await page.setViewportSize({ width: 1000, height: 450 });
  await expect(graph.getByTestId('graph-tool-panel')).toHaveAttribute('data-mode', 'sheet');
  await expect(graph.locator('canvas').first()).toHaveAttribute('data-instance-marker', 'same-graph');
  await graph.getByRole('button', { name: 'Bereich schließen' }).click();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(graph.getByTestId('graph-tool-panel')).toHaveCount(0);
  await page.evaluate(() => localStorage.setItem('doctus-language', 'en'));
  await page.reload();
  await expect(page.getByTestId('knowledge-graph-view')).toBeVisible();
  await page.evaluate(() => document.documentElement.style.setProperty('--ds-ui-scale', '1.5'));
  await page.setViewportSize({ width: 1000, height: 450 });
  const toolbar = page.getByTestId('graph-toolbar');
  await expect.poll(() => toolbar.evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1);
  await page.getByTestId('knowledge-graph-view').getByRole('button', { name: 'Filters', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Filters', exact: true })).toBeVisible();
});

test('clearing a pinned selection restores the actual canvas opacity without rebuilding the graph', async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const booking = nodes.find(node => node.label === 'Booking processor')!;
  await page.addInitScript(({ x, y }) => {
    const state = window as Window & { graphTestNodeAlpha?: number };
    const target = new WeakSet<CanvasRenderingContext2D>();
    const arc = CanvasRenderingContext2D.prototype.arc;
    const fill = CanvasRenderingContext2D.prototype.fill;
    CanvasRenderingContext2D.prototype.arc = function (cx, cy, radius, start, end, counterclockwise) {
      if (Math.abs(cx - x) < 0.001 && Math.abs(cy - y) < 0.001) target.add(this);
      else target.delete(this);
      return arc.call(this, cx, cy, radius, start, end, counterclockwise);
    };
    CanvasRenderingContext2D.prototype.fill = function (this: CanvasRenderingContext2D, ...args: unknown[]) {
      // Read the node fill, independently of zoom-dependent labels and icons.
      if (target.has(this) && this.canvas.isConnected) state.graphTestNodeAlpha = this.globalAlpha;
      return Reflect.apply(fill, this, args);
    };
  }, { x: booking.fx, y: booking.fy });
  const graph = await openGraph(page, baseURL!, 1, 50);
  await graph.locator('canvas').first().evaluate(canvas => canvas.setAttribute('data-focus-reset-marker', 'original'));
  await graph.getByRole('button', { name: 'Auf diesen Knoten fokussieren', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as Window & { graphTestNodeAlpha?: number }).graphTestNodeAlpha)).toBe(0.15);

  await graph.getByRole('button', { name: 'Fokus aufheben', exact: true }).click();

  await expect.poll(() => page.evaluate(() => (window as Window & { graphTestNodeAlpha?: number }).graphTestNodeAlpha)).toBe(1);
  await expect(graph.getByRole('button', { name: 'Fokus aufheben', exact: true })).toHaveCount(0);
  await expect(graph.getByTestId('graph-tool-panel')).toHaveCount(0);
  await expect(graph.locator('canvas').first()).toHaveAttribute('data-focus-reset-marker', 'original');
});
