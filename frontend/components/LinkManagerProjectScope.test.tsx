import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { LinkManagerView } from './LinkManagerView';

vi.mock('./TopicsPanel', () => ({ TopicsPanel: () => null }));
const projectA = { id: 2, name: 'Syncope' };
const projectB = { id: 3538, name: 'Spring WS' };
const json = (value: unknown) => ({ ok: true, json: async () => value });
const link = {
  id: 50, source_a: { type: 'document', title: 'Syncope-only result' },
  source_b: { type: 'document', title: 'Syncope manual' }, score: 0.8,
  link_type: 'semantic', status: 'pending', context: 'Syncope analysis', created_by: 'auto',
};
const view = (project: typeof projectA | null) => <LanguageProvider><LinkManagerView selectedProject={project} theme="dark" /></LanguageProvider>;

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(600);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('scopes link lists and counts, clears old results on project change and ignores late replies', async () => {
  let releaseOldCounts!: (value: unknown) => void;
  let delayCounts = false;
  const fetchMock = vi.fn(async (url: string) => {
    const parsed = new URL(url);
    if (parsed.pathname.endsWith('/knowledge-sources')) return json([]);
    if (parsed.pathname.endsWith('/link-recommendations')) return json({ links: [], counts: {} });
    if (parsed.pathname === '/knowledge-links/counts') {
      if (delayCounts && parsed.searchParams.get('project_id') === '2') {
        return new Promise(resolve => { releaseOldCounts = resolve; });
      }
      return json({ pending: parsed.searchParams.get('project_id') === '2' ? 1 : 0 });
    }
    if (parsed.pathname === '/knowledge-links') return json(parsed.searchParams.get('project_id') === '2' ? [link] : []);
    return json({});
  });
  vi.stubGlobal('fetch', fetchMock);
  const rendered = render(view(projectA));
  expect(await screen.findByText('Syncope-only result')).toBeTruthy();
  delayCounts = true;
  // Remount A so its response is still outstanding when B is selected.
  rendered.rerender(view(null));
  rendered.rerender(view(projectA));
  await waitFor(() => expect(releaseOldCounts).toBeTypeOf('function'));
  rendered.rerender(view(projectB));
  await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url.includes('project_id=3538'))).toBe(true));
  await act(async () => releaseOldCounts(json({ pending: 99 })));
  expect(screen.queryByText('Syncope-only result')).toBeNull();
  expect(screen.queryByText('99')).toBeNull();
  for (const [url] of fetchMock.mock.calls) {
    if (new URL(url).pathname.startsWith('/knowledge-links')) expect(new URL(url).searchParams.has('project_id')).toBe(true);
  }
});

it('never requests global link data without a selected project', async () => {
  const fetchMock = vi.fn(async () => json([])); vi.stubGlobal('fetch', fetchMock);
  render(view(null));
  await act(async () => {});
  expect(fetchMock).not.toHaveBeenCalled();
});
