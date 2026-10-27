// Run against an isolated frontend; all API calls are intercepted in the browser.
// GRAPH_BENCH_URL=http://localhost:3100 node scripts/benchmark-knowledge-graph.cjs <output.json>
const { chromium } = require('playwright');
const fs = require('node:fs');
const os = require('node:os');
const { execFileSync } = require('node:child_process');

const baseURL = process.env.GRAPH_BENCH_URL || 'http://localhost:3100';
const counts = (process.env.GRAPH_BENCH_NODES || '2000,20000').split(',').map(Number);
const output = process.argv[2];
if (!output) throw new Error('Provide an output JSON path.');

function corpus(count) {
  const nodes = Array.from({ length: count }, (_, i) => ({
    id: `file:${i}`, type: 'code_file', label: `Service${i}.java`, file_path: `src/Service${i}.java`,
    project_id: 1, source_id: 1, source_type: 'Git',
    fx: (i % Math.ceil(Math.sqrt(count))) * 180,
    fy: Math.floor(i / Math.ceil(Math.sqrt(count))) * 180,
  }));
  const edges = nodes.flatMap((node, i) => [1, 17].map(offset => ({
    id: `edge:${i}:${offset}`, source: node.id, target: nodes[(i + offset) % count].id,
    link_type: 'code_dependency', direction: 'directed', score: null, context: null,
  })));
  return { nodes, edges };
}

async function measure(page, action) {
  await page.evaluate(() => {
    window.graphBench.draws = 0;
    window.graphBench.styles = 0;
    window.graphBench.frames = [];
    window.graphBench.sample = true;
  });
  await action();
  return page.evaluate(() => {
    const state = window.graphBench;
    state.sample = false;
    const intervals = state.frames.slice(1).map((time, i) => time - state.frames[i]).sort((a, b) => a - b);
    return {
      canvasArcCalls: state.draws, computedStyleCalls: state.styles,
      frameIntervalP95Ms: intervals[Math.floor(intervals.length * 0.95)] || null,
      observedFps: intervals.length ? 1000 / (intervals.reduce((a, b) => a + b, 0) / intervals.length) : null,
    };
  });
}

(async () => {
  const browser = await chromium.launch({ headless: true,
    executablePath: process.env.GRAPH_BENCH_CHROMIUM,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const results = [];
  try {
    for (const count of counts) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => {
        window.graphBench = { draws: 0, styles: 0, frames: [], sample: false, point: null };
        const style = window.getComputedStyle;
        window.getComputedStyle = function (...args) {
          if (window.graphBench.sample) window.graphBench.styles++;
          return style.apply(this, args);
        };
        const clear = CanvasRenderingContext2D.prototype.clearRect;
        CanvasRenderingContext2D.prototype.clearRect = function (...args) {
          if (this.canvas.isConnected) window.graphBench.point = null;
          return clear.apply(this, args);
        };
        const arc = CanvasRenderingContext2D.prototype.arc;
        CanvasRenderingContext2D.prototype.arc = function (x, y, r, ...args) {
          const state = window.graphBench;
          if (state.sample) state.draws++;
          if (r >= 17 && this.canvas.isConnected) {
            const point = this.getTransform().transformPoint({ x, y });
            const rect = this.canvas.getBoundingClientRect();
            const px = point.x / (this.canvas.width / rect.width);
            const py = point.y / (this.canvas.height / rect.height);
            if (px > 40 && py > 40 && px < rect.width - 40 && py < rect.height - 40) {
              const distance = Math.hypot(px - rect.width / 2, py - rect.height / 2);
              if (!state.point || distance < state.point.distance) {
                state.point = { x: rect.x + px, y: rect.y + py, distance };
              }
            }
          }
          return arc.call(this, x, y, r, ...args);
        };
        function frame(time) {
          if (window.graphBench.sample) window.graphBench.frames.push(time);
          requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
      });
      const graph = corpus(count);
      const project = { id: 1, name: 'Graph performance audit', status: 'completed' };
      const session = { id: 9001, uuid: 'graph-performance', title: 'Performance session', project_id: 1,
        snapshot_json: { panelConfigs: ['graph'], panelFrozen: [false], selectedProjectId: 1,
          panelSelections: [{ selectedFile: null, selectedEntity: null, selectedDoc: null }] } };
      await context.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.origin === new URL(baseURL).origin) return route.continue();
        let body = [];
        if (url.pathname === '/auth/me') body = { id: 1, username: 'graph-audit', is_admin: true };
        else if (url.pathname === '/projects') body = [project];
        else if (url.pathname === '/chat/sessions/page') body = { sessions: [session], has_more: false, limit: 30 };
        else if (url.pathname.startsWith('/chat/sessions/by-uuid/')) body = session;
        else if (url.pathname === '/graph') body = graph;
        else if (url.pathname === '/knowledge-sources') body = [{ id: 1, project_id: 1, name: 'Java fixture', type: 'Git', sync_status: 'completed' }];
        else if (url.pathname === '/model-info') body = { llm: 'audit', embedding: 'audit' };
        else if (url.pathname === '/models') body = { models: [] };
        await route.fulfill({ status: 200, headers: { 'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': new URL(baseURL).origin, 'Access-Control-Allow-Credentials': 'true',
          'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*' }, body: JSON.stringify(body) });
      });
      await page.goto(baseURL);
      await page.locator('#project-selector').click();
      await page.getByRole('option', { name: project.name }).click();
      const start = Date.now();
      await page.getByText(session.title, { exact: true }).first().click();
      const view = page.getByTestId('knowledge-graph-view');
      await view.locator('canvas').first().waitFor({ timeout: 60000 });
      const firstCanvasMs = Date.now() - start;
      await page.waitForTimeout(10500);
      await view.getByRole('button', { name: 'Alles einpassen' }).click();
      await page.waitForTimeout(1000);
      const idle = await measure(page, () => page.waitForTimeout(1800));
      const point = await page.evaluate(() => window.graphBench.point);
      if (!point) throw new Error(`No drawable node found for ${count} nodes`);
      await page.mouse.click(point.x, point.y);
      await page.waitForTimeout(1000);
      const selectedVerified = await view.getByTestId('graph-tool-panel').count() > 0;
      const selected = await measure(page, () => page.waitForTimeout(1800));
      const interaction = await measure(page, async () => {
        for (let i = 0; i < 12; i++) {
          await page.mouse.wheel(0, i < 6 ? -100 : 100);
          await page.waitForTimeout(80);
        }
        await page.waitForTimeout(600);
      });
      const result = { nodes: count, edges: graph.edges.length, firstCanvasMs, selectedVerified, idle, selected, interaction, errors };
      results.push(result);
      console.log(JSON.stringify(result));
      await context.close();
    }
  } finally {
    await browser.close();
    let revision;
    try { revision = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(); } catch { revision = process.env.GRAPH_BENCH_REVISION; }
    fs.writeFileSync(output, JSON.stringify({ revision, date: new Date().toISOString(),
      environment: { cpu: os.cpus()[0]?.model, cpus: os.cpus().length, browser: 'headless Chromium',
        viewport: '1440x900', fixture: 'fixed grid, two directed edges per node; rendering benchmark, excludes layout quality and database' }, results }, null, 2));
  }
})();
