import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const apiMocks = vi.hoisted(() => ({ fetch: vi.fn() }));

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({ t: (key: string) => key }),
}));

import { TopicsPanel } from './TopicsPanel';

function jsonResponse(data: unknown, init: { ok?: boolean; status?: number } = {}) {
  return { ok: init.ok ?? true, status: init.status ?? 200, json: async () => data };
}

const topicA = { id: 1, name: 'Zahlungsverkehr', description: 'Alles rund um Zahlungen', color: 'indigo', node_count: 0, created_at: null };
const topicB = { id: 2, name: 'Kernbanking', description: null, color: 'emerald', node_count: 0, created_at: null };

/** Fetch-Stub, der nach URL/Methode routet -- analog CallGraphView.test.tsx. */
function stubFetch(options: {
  topics?: unknown[];
  nodesByTopic?: Record<number, unknown[]>;
  searchResults?: unknown[];
  createResponse?: { ok?: boolean; status?: number; body?: unknown };
  patchResponse?: { ok?: boolean; status?: number; body?: unknown };
  attachResponse?: { ok?: boolean; status?: number; body?: unknown };
} = {}) {
  let topics = options.topics ?? [];
  const nodesByTopic: Record<number, unknown[]> = options.nodesByTopic ?? {};

  return vi.fn(async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase();
    const body = init?.body ? JSON.parse(init.body as string) : undefined;

    if (url.includes('/topics/search-nodes')) {
      return jsonResponse(options.searchResults ?? []);
    }
    const nodesMatch = url.match(/\/topics\/(\d+)\/nodes(?:\/(\d+))?$/);
    if (nodesMatch) {
      const topicId = Number(nodesMatch[1]);
      if (method === 'GET') return jsonResponse(nodesByTopic[topicId] ?? []);
      if (method === 'POST') {
        const r = options.attachResponse ?? {};
        return jsonResponse(r.body ?? { id: 999, topic_id: topicId, ...body }, r);
      }
      if (method === 'DELETE') return jsonResponse({ message: 'Node removed' });
    }
    const topicMatch = url.match(/\/topics\/(\d+)$/);
    if (topicMatch && method === 'PATCH') {
      const r = options.patchResponse ?? {};
      const existing = topics.find((t) => (t as { id: number }).id === Number(topicMatch[1])) as Record<string, unknown> | undefined;
      return jsonResponse(r.body ?? { ...existing, ...body }, r);
    }
    if (topicMatch && method === 'DELETE') {
      return jsonResponse({ message: 'Topic deleted' });
    }
    if (url.endsWith('/topics') && method === 'GET') return jsonResponse(topics);
    if (url.endsWith('/topics') && method === 'POST') {
      const r = options.createResponse ?? {};
      const created = r.body ?? { id: 999, node_count: 0, created_at: null, ...body };
      topics = [created, ...topics];
      return jsonResponse(created, r);
    }
    throw new Error(`Unerwarteter Fetch-Aufruf: ${method} ${url}`);
  });
}

function colorSwatch(container: HTMLElement, color: string): HTMLElement {
  return Array.from(container.querySelectorAll('button')).find((b) => b.className.includes(`bg-ds-${color}-500`))!;
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('TopicsPanel — Themenliste', () => {
  it('loads and lists all topics with their node count', async () => {
    apiMocks.fetch.mockImplementation(stubFetch({ topics: [{ ...topicA, node_count: 2 }, topicB] }));
    render(<TopicsPanel theme="dark" />);

    expect(await screen.findByText('Zahlungsverkehr')).toBeTruthy();
    expect(screen.getByText('Kernbanking')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
  });

  it('shows the empty state when there are no topics yet', async () => {
    apiMocks.fetch.mockImplementation(stubFetch({ topics: [] }));
    render(<TopicsPanel theme="dark" />);
    expect(await screen.findByText('topicsPanel.noTopicsYet')).toBeTruthy();
  });

  it('filters the topic list by name on the client, without another request', async () => {
    apiMocks.fetch.mockImplementation(stubFetch({ topics: [topicA, topicB] }));
    render(<TopicsPanel theme="dark" />);
    await screen.findByText('Kernbanking');
    const callsBeforeFilter = apiMocks.fetch.mock.calls.length;

    fireEvent.change(screen.getByPlaceholderText('topicsPanel.searchPlaceholder'), { target: { value: 'Kern' } });

    expect(screen.getByText('Kernbanking')).toBeTruthy();
    expect(screen.queryByText('Zahlungsverkehr')).toBeNull();
    expect(apiMocks.fetch.mock.calls.length).toBe(callsBeforeFilter);
  });

  it('shows the no-selection hint before any topic is picked', async () => {
    apiMocks.fetch.mockImplementation(stubFetch({ topics: [topicA] }));
    render(<TopicsPanel theme="dark" />);
    await screen.findByText('Zahlungsverkehr');
    expect(screen.getByText('topicsPanel.selectTopic')).toBeTruthy();
  });
});

describe('TopicsPanel — Knoten eines Themas', () => {
  const nodeEntity = { id: 10, topic_id: 1, node_type: 'entity', node_id: 5, node_label: 'DISPATCHER-PARA', node_url: null, node_meta: null };
  const nodeProject = { id: 11, topic_id: 1, node_type: 'project', node_id: 2, node_label: 'Kernbanking', node_url: null, node_meta: null };

  it('loads and groups the nodes of the selected topic by node type', async () => {
    apiMocks.fetch.mockImplementation(stubFetch({
      topics: [{ ...topicA, node_count: 2 }],
      nodesByTopic: { 1: [nodeEntity, nodeProject] },
    }));
    render(<TopicsPanel theme="dark" />);

    fireEvent.click(await screen.findByText('Zahlungsverkehr'));

    expect(await screen.findByText('DISPATCHER-PARA')).toBeTruthy();
    expect(screen.getByText('Kernbanking', { selector: 'span' })).toBeTruthy();
    expect(screen.getByText('topicsPanel.nodeTypes.entity')).toBeTruthy();
    expect(screen.getByText('topicsPanel.nodeTypes.project')).toBeTruthy();
  });

  it('shows a hint when the selected topic has no nodes yet', async () => {
    apiMocks.fetch.mockImplementation(stubFetch({ topics: [topicA], nodesByTopic: { 1: [] } }));
    render(<TopicsPanel theme="dark" />);

    fireEvent.click(await screen.findByText('Zahlungsverkehr'));
    expect(await screen.findByText('topicsPanel.noNodesYet')).toBeTruthy();
  });
});

describe('TopicsPanel — Thema anlegen', () => {
  it('requires a name before creating anything', async () => {
    const fetchMock = stubFetch({ topics: [] });
    apiMocks.fetch.mockImplementation(fetchMock);
    render(<TopicsPanel theme="dark" />);
    await screen.findByText('topicsPanel.noTopicsYet');

    fireEvent.click(screen.getByText('topicsPanel.newTopicButton'));
    fireEvent.click(screen.getByText('topicsPanel.createButton'));

    expect(await screen.findByText('topicsPanel.errors.nameRequired')).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining('/topics'), expect.objectContaining({ method: 'POST' }));
  });

  it('creates a topic with the chosen color, selects it and resets the form', async () => {
    const fetchMock = stubFetch({ topics: [] });
    apiMocks.fetch.mockImplementation(fetchMock);
    const { container } = render(<TopicsPanel theme="dark" />);
    await screen.findByText('topicsPanel.noTopicsYet');

    fireEvent.click(screen.getByText('topicsPanel.newTopicButton'));
    fireEvent.change(screen.getByPlaceholderText('topicsPanel.namePlaceholder'), { target: { value: '  Neues Thema  ' } });
    fireEvent.change(screen.getByPlaceholderText('topicsPanel.descriptionPlaceholder'), { target: { value: '  Kurzbeschreibung  ' } });
    fireEvent.click(colorSwatch(container, 'emerald'));
    fireEvent.click(screen.getByText('topicsPanel.createButton'));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/topics',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ name: 'Neues Thema', description: 'Kurzbeschreibung', color: 'emerald' }) }),
    ));

    // Neu angelegtes Thema ist selektiert (Detailkopf zeigt seinen Namen) und
    // das Anlage-Formular ist wieder eingeklappt.
    expect(await screen.findByRole('heading', { name: 'Neues Thema' })).toBeTruthy();
    expect(screen.queryByPlaceholderText('topicsPanel.namePlaceholder')).toBeNull();
  });

  it('shows an inline error and keeps the form open when creation fails', async () => {
    apiMocks.fetch.mockImplementation(stubFetch({ topics: [], createResponse: { ok: false, status: 500 } }));
    render(<TopicsPanel theme="dark" />);
    await screen.findByText('topicsPanel.noTopicsYet');

    fireEvent.click(screen.getByText('topicsPanel.newTopicButton'));
    fireEvent.change(screen.getByPlaceholderText('topicsPanel.namePlaceholder'), { target: { value: 'Thema' } });
    fireEvent.click(screen.getByText('topicsPanel.createButton'));

    expect(await screen.findByText('topicsPanel.errors.createFailed')).toBeTruthy();
    expect(screen.getByPlaceholderText('topicsPanel.namePlaceholder')).toBeTruthy();
  });

  it('submits on Enter in the name field', async () => {
    const fetchMock = stubFetch({ topics: [] });
    apiMocks.fetch.mockImplementation(fetchMock);
    render(<TopicsPanel theme="dark" />);
    await screen.findByText('topicsPanel.noTopicsYet');

    fireEvent.click(screen.getByText('topicsPanel.newTopicButton'));
    const nameInput = screen.getByPlaceholderText('topicsPanel.namePlaceholder');
    fireEvent.change(nameInput, { target: { value: 'Per Enter' } });
    fireEvent.keyDown(nameInput, { key: 'Enter' });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('http://api.test/topics', expect.objectContaining({ method: 'POST' })));
  });
});

describe('TopicsPanel — Thema bearbeiten und löschen', () => {
  it('prefills the edit form and saves the renamed topic', async () => {
    const fetchMock = stubFetch({ topics: [topicA] });
    apiMocks.fetch.mockImplementation(fetchMock);
    render(<TopicsPanel theme="dark" />);
    fireEvent.click(await screen.findByText('Zahlungsverkehr'));
    await screen.findByRole('heading', { name: 'Zahlungsverkehr' });

    fireEvent.click(screen.getByTitle('topicsPanel.editTitle'));
    const nameInput = screen.getByDisplayValue('Zahlungsverkehr');
    fireEvent.change(nameInput, { target: { value: 'Zahlungsverkehr (neu)' } });
    fireEvent.click(screen.getByText('topicsPanel.saveButton'));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/topics/1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ name: 'Zahlungsverkehr (neu)', description: 'Alles rund um Zahlungen', color: 'indigo' }),
      }),
    ));
    expect(await screen.findByRole('heading', { name: 'Zahlungsverkehr (neu)' })).toBeTruthy();
  });

  it('does not save when the name is cleared', async () => {
    const fetchMock = stubFetch({ topics: [topicA] });
    apiMocks.fetch.mockImplementation(fetchMock);
    render(<TopicsPanel theme="dark" />);
    fireEvent.click(await screen.findByText('Zahlungsverkehr'));
    await screen.findByRole('heading', { name: 'Zahlungsverkehr' });

    fireEvent.click(screen.getByTitle('topicsPanel.editTitle'));
    fireEvent.change(screen.getByDisplayValue('Zahlungsverkehr'), { target: { value: '' } });
    const callsBeforeSave = fetchMock.mock.calls.length;
    fireEvent.click(screen.getByText('topicsPanel.saveButton'));

    expect(fetchMock.mock.calls.length).toBe(callsBeforeSave);
  });

  it('deletes the selected topic and clears the selection', async () => {
    const fetchMock = stubFetch({ topics: [topicA] });
    apiMocks.fetch.mockImplementation(fetchMock);
    render(<TopicsPanel theme="dark" />);
    fireEvent.click(await screen.findByText('Zahlungsverkehr'));
    await screen.findByRole('heading', { name: 'Zahlungsverkehr' });

    fireEvent.click(screen.getByTitle('topicsPanel.deleteTopicTitle'));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('http://api.test/topics/1', expect.objectContaining({ method: 'DELETE' })));
    expect(await screen.findByText('topicsPanel.selectTopic')).toBeTruthy();
    expect(screen.queryByText('Zahlungsverkehr')).toBeNull();
  });
});

describe('TopicsPanel — Knoten hinzufügen/entfernen', () => {
  const searchHit = { node_type: 'entity', node_id: 5, node_label: 'HAUPT', node_url: null, node_meta: null };

  it('attaches a search result, shows it grouped and bumps the sidebar count', async () => {
    const fetchMock = stubFetch({ topics: [topicA], nodesByTopic: { 1: [] }, searchResults: [searchHit] });
    apiMocks.fetch.mockImplementation(fetchMock);
    render(<TopicsPanel theme="dark" />);
    fireEvent.click(await screen.findByText('Zahlungsverkehr'));
    await screen.findByText('topicsPanel.noNodesYet');

    fireEvent.click(screen.getByText('topicsPanel.addNodeButton'));
    fireEvent.change(screen.getByPlaceholderText(/topicsPanel.searchTypePlaceholder/), { target: { value: 'HAUPT' } });

    fireEvent.click(await screen.findByText('HAUPT'));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/topics/1/nodes',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ node_type: 'entity', node_id: 5, node_label: 'HAUPT', node_url: null, node_meta: null }),
      }),
    ));
    // Der Knoten erscheint jetzt in der Liste (nicht mehr nur im Suchresultat)
    // und die Sidebar-Zählung des Themas steigt von 0 auf 1.
    await waitFor(() => expect(screen.getAllByText('HAUPT')).toHaveLength(1));
    expect(screen.getByText('1')).toBeTruthy();
  });

  it('shows an inline error without adding the node when it is already linked (409)', async () => {
    apiMocks.fetch.mockImplementation(stubFetch({
      topics: [topicA], nodesByTopic: { 1: [] }, searchResults: [searchHit],
      attachResponse: { ok: false, status: 409 },
    }));
    render(<TopicsPanel theme="dark" />);
    fireEvent.click(await screen.findByText('Zahlungsverkehr'));
    await screen.findByText('topicsPanel.noNodesYet');

    fireEvent.click(screen.getByText('topicsPanel.addNodeButton'));
    fireEvent.change(screen.getByPlaceholderText(/topicsPanel.searchTypePlaceholder/), { target: { value: 'HAUPT' } });
    fireEvent.click(await screen.findByText('HAUPT'));

    expect(await screen.findByText('topicsPanel.errors.alreadyLinked')).toBeTruthy();
    expect(screen.getByText('topicsPanel.noNodesYet')).toBeTruthy();
  });

  it('shows a generic inline error when attaching otherwise fails', async () => {
    apiMocks.fetch.mockImplementation(stubFetch({
      topics: [topicA], nodesByTopic: { 1: [] }, searchResults: [searchHit],
      attachResponse: { ok: false, status: 500 },
    }));
    render(<TopicsPanel theme="dark" />);
    fireEvent.click(await screen.findByText('Zahlungsverkehr'));
    await screen.findByText('topicsPanel.noNodesYet');

    fireEvent.click(screen.getByText('topicsPanel.addNodeButton'));
    fireEvent.change(screen.getByPlaceholderText(/topicsPanel.searchTypePlaceholder/), { target: { value: 'HAUPT' } });
    fireEvent.click(await screen.findByText('HAUPT'));

    expect(await screen.findByText('topicsPanel.errors.linkFailed')).toBeTruthy();
  });

  it('detaches a node and decrements the sidebar count', async () => {
    const attached = { id: 10, topic_id: 1, node_type: 'entity', node_id: 5, node_label: 'HAUPT', node_url: null, node_meta: null };
    const fetchMock = stubFetch({ topics: [{ ...topicA, node_count: 1 }], nodesByTopic: { 1: [attached] } });
    apiMocks.fetch.mockImplementation(fetchMock);
    render(<TopicsPanel theme="dark" />);
    fireEvent.click(await screen.findByText('Zahlungsverkehr'));
    await screen.findByText('HAUPT');
    expect(screen.getByText('1')).toBeTruthy();

    fireEvent.click(screen.getByText('HAUPT').closest('div')!.querySelector('button')!);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('http://api.test/topics/1/nodes/10', expect.objectContaining({ method: 'DELETE' })));
    await waitFor(() => expect(screen.queryByText('HAUPT')).toBeNull());
    expect(screen.getByText('0')).toBeTruthy();
  });
});

describe('TopicsPanel — Knotensuche (Nahtstelle zu O-111)', () => {
  it('searches immediately with an empty query for the project type, but waits for input on the entity type', async () => {
    const fetchMock = stubFetch({ topics: [topicA], nodesByTopic: { 1: [] } });
    apiMocks.fetch.mockImplementation(fetchMock);
    render(<TopicsPanel theme="dark" />);
    fireEvent.click(await screen.findByText('Zahlungsverkehr'));
    await screen.findByText('topicsPanel.noNodesYet');

    fireEvent.click(screen.getByText('topicsPanel.addNodeButton'));
    // Default-Typ ist 'project' -- die Suche läuft nach der Debounce-Zeit auch
    // mit leerem Suchtext an (Browsing-Verhalten, siehe TopicsPanel.tsx).
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('types=project'),
    ), { timeout: 1000 });
    const callsAfterProjectSearch = fetchMock.mock.calls.filter((c) => String(c[0]).includes('search-nodes')).length;

    fireEvent.click(screen.getByText('topicsPanel.nodeTypes.entity'));
    await new Promise((resolve) => setTimeout(resolve, 400));
    const callsAfterEntitySwitch = fetchMock.mock.calls.filter((c) => String(c[0]).includes('search-nodes')).length;
    expect(callsAfterEntitySwitch).toBe(callsAfterProjectSearch);

    fireEvent.change(screen.getByPlaceholderText(/topicsPanel.searchTypePlaceholder/), { target: { value: 'DISPATCHER' } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/types=entity.*q=DISPATCHER|q=DISPATCHER.*types=entity/),
    ), { timeout: 1000 });
  });
});
