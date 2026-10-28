import { afterEach, expect, it } from 'vitest';
import { addWebAnchorScroll, addWebOriginTheme } from './webDocumentHtml';

afterEach(() => document.documentElement.removeAttribute('style'));

it('resolves the current theme tokens for the isolated Jira document', () => {
  const style = document.documentElement.style;
  style.setProperty('--ds-foreground', '236 247 242');
  style.setProperty('--ds-background', '14 30 30');
  style.setProperty('--ds-accent', '0 100 210');
  style.setProperty('--ds-surface-muted', '30 58 54');
  const html = addWebOriginTheme('<p>Ticket</p>', 'dark', 'jira');
  expect(html).toContain('color:rgb(236 247 242)!important');
  expect(html).toContain('background:rgb(14 30 30)!important');
  expect(html).toContain('background:rgb(30 58 54)!important');
  expect(html).not.toContain('var(--ds-');
  expect(addWebOriginTheme('<p>Page</p>', 'dark', 'confluence')).toBe('<p>Page</p>');
});

it('keeps an anchor from terminating the injected script', () => {
  const html = addWebAnchorScroll('<body>Page</body>', '#</script><script>bad()</script>');
  expect(html.match(/<script>/g)).toHaveLength(1);
  expect(html).toContain('\\u003c/script>');
  expect(html).toMatch(/<\/script><\/body>$/);
});
