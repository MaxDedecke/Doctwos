import { afterEach, expect, it } from 'vitest';
import { addWebAnchorScroll, buildWebDocumentHtml, type WebDocumentData } from './webDocumentHtml';

afterEach(() => document.documentElement.removeAttribute('style'));

const DOC: WebDocumentData = {
  title: 'T', kind: 'page', facts: [], breadcrumbs: [], body_html: '<p>Seite</p>', comments: [], attachments: [], related: [], extra_css: '', origin: 'live',
};
const LABELS = { empty: 'Leer', comments: (shown: number, total: number) => `K ${shown}/${total}`, formatDate: (value: string) => `D:${value}` };
const build = (doc: Partial<WebDocumentData>) => buildWebDocumentHtml({ ...DOC, ...doc }, 'dark', 'http://api', LABELS);

it('resolves the current theme tokens for the isolated document of every system', () => {
  const style = document.documentElement.style;
  for (const token of ['surface-muted', 'border', 'foreground-muted', 'accent', 'danger-base', 'warning-base', 'success-base']) style.setProperty(`--ds-${token}`, '1 2 3');
  style.setProperty('--ds-foreground', '236 247 242');
  style.setProperty('--ds-background', '14 30 30');
  const html = build({ extra_css: '.macro{color:var(--wd-accent)}' });
  expect(html).toContain('--wd-fg:rgb(236 247 242)');
  expect(html).toContain('--wd-bg:rgb(14 30 30)');
  expect(html).toContain('color-scheme:dark');
  expect(html).toContain('.macro{color:var(--wd-accent)}');
  expect(html).not.toContain('var(--ds-');
});

it('survives sanitizing: scripts go, known link marks stay, links open apart, anchors stay in the page', () => {
  const html = build({
    body_html: '<script>bad()</script><a href="#s" id="i">A</a><a href="https://x" data-doctus-url="https://x" data-doctus-source="3" target="_self">B</a><a href="javascript:bad()">C</a>',
  });
  const page = new DOMParser().parseFromString(html, 'text/html');
  expect(page.querySelector('main script')).toBeNull();
  expect(html).not.toContain('bad()');
  expect(page.querySelector('a[href="#s"]')?.getAttribute('target')).toBeNull();
  const known = page.querySelector('a[data-doctus-source="3"]');
  expect(known?.getAttribute('target')).toBe('_blank');
  expect(known?.getAttribute('rel')).toBe('noopener noreferrer');
});

it('points signed images at the API and leaves foreign ones alone', () => {
  const html = build({ body_html: '<img src="/knowledge-sources/1/web-asset?token=t"><img src="https://x/y.png">' });
  expect(html).toContain('src="http://api/knowledge-sources/1/web-asset?token=t"');
  expect(html).toContain('src="https://x/y.png"');
});

it('shows comments with escaped authors, partial counts and an empty body notice', () => {
  const html = build({
    body_html: '  ', comments_total: 3,
    comments: [{ author: '<b>Ada</b>', created: '2026', body_html: '<p>Hallo</p><script>bad()</script>' }],
  });
  expect(html).toContain('Leer');
  expect(html).toContain('K 1/3');
  expect(html).toContain('&lt;b&gt;Ada&lt;/b&gt; · D:2026');
  expect(html).not.toContain('bad()');
  expect(build({})).not.toContain('wd-comment"');
});

it('keeps a style end tag of an adapter from breaking out', () => {
  expect(build({ extra_css: '</style><script>bad()</script>' }).match(/<\/style>/g)).toHaveLength(1);
});

it('keeps an anchor from terminating the injected script', () => {
  const html = addWebAnchorScroll('<body>Page</body>', '#</script><script>bad()</script>');
  expect(html.match(/<script>/g)).toHaveLength(1);
  expect(html).toContain('\\u003c/script>');
  expect(html).toMatch(/<\/script><\/body>$/);
});
