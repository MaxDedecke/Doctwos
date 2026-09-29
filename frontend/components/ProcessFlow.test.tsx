import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { ProcessView } from './CallGraphView';

vi.mock('react-force-graph-2d', () => ({ default: () => <div data-testid="process-graph" /> }));

const loc = (line: number) => ({ file_path: 'MAIN.CBL', start_line: line, source_id: 5 });
const N = (id: string, label: string, kind = 'step') => ({ id, kind, label, language: 'cobol', entity_id: id.startsWith('entity:') ? Number(id.split(':')[1]) : null, locator: loc(1) });
const T = (id: string, source: string, target: string, kind: string, line: number, types: string[], certainty = 'certain') =>
  ({ id, source, target, kind, certainty, resolution: 'resolved', code_edge_types: types, locator: loc(line), meta: {} });

const ROOT = {
  nodes: [N('entity:1', 'MAIN', 'entry'), N('entity:2', 'INIT'), N('entity:3', 'WRITE-OUT'), N('entity:9', 'ACCT-ID', 'data_access'), N('external:edge:5', 'BANK-AUTH', 'external_call')],
  transitions: [
    T('t2', 'entity:1', 'entity:3', 'call', 40, ['PERFORM']),
    T('t1', 'entity:1', 'entity:2', 'call', 20, ['PERFORM']),
    T('d1', 'entity:1', 'entity:9', 'data_access', 10, ['READS']),
    T('d2', 'entity:1', 'entity:9', 'data_access', 11, ['WRITES']),
    T('x1', 'entity:1', 'external:edge:5', 'external_call', 30, ['CALL'], 'unresolved'),
  ],
  truncation: { truncated: false, reasons: [] },
};
const INIT = {
  nodes: [N('entity:2', 'INIT'), N('entity:4', 'OPEN-FILES')],
  transitions: [T('s1', 'entity:2', 'entity:4', 'call', 55, ['PERFORM'])],
  truncation: { truncated: false, reasons: [] },
};

function setup() {
  const fetchMock = vi.fn(async (url: string) => ({ ok: true, json: async () => (url.includes('entity_id=2&') ? INIT : ROOT) }));
  vi.stubGlobal('fetch', fetchMock);
  const onFileSelect = vi.fn();
  render(<LanguageProvider><ProcessView theme="dark" focusedEntity={{ id: 1, name: 'MAIN' }} onFileSelect={onFileSelect} projectId={3} /></LanguageProvider>);
  return { fetchMock, onFileSelect };
}

describe('ProcessView – Ablauf', () => {
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it('zeigt Schritte in Zeilenreihenfolge, Datenzugriffe gebündelt und offene Aufrufe in ihrer Bahn', async () => {
    setup();
    await screen.findByText('INIT');
    const rows = screen.getAllByRole('row').map(row => row.textContent ?? '');
    const order = ['MAIN', '1× liest · 1× schreibt', 'INIT', 'BANK-AUTH', 'WRITE-OUT'];
    const positions = order.map(text => rows.findIndex(row => row.includes(text)));
    expect(positions.every(p => p >= 0)).toBe(true);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
    expect(screen.getByText('offen')).toBeTruthy();
  });

  it('lädt Unterschritte erst beim Aufklappen nach und öffnet Quellstellen', async () => {
    const { fetchMock, onFileSelect } = setup();
    await screen.findByText('INIT');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('OPEN-FILES')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'INIT aufklappen' }));
    await screen.findByText('OPEN-FILES');
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toContain('entity_id=2&hops=1');

    fireEvent.click(screen.getByRole('button', { name: 'INIT einklappen' }));
    expect(screen.queryByText('OPEN-FILES')).toBeNull();

    fireEvent.click(screen.getByText('WRITE-OUT'));
    expect(onFileSelect).toHaveBeenCalledWith('MAIN.CBL', 40, 5);
  });

  it('klappt gebündelte Datenzugriffe einzeln auf', async () => {
    setup();
    const summary = await screen.findByText('1× liest · 1× schreibt');
    expect(screen.queryByText('schreibt')).toBeNull();
    fireEvent.click(summary);
    const row = summary.closest('[role="row"]') as HTMLElement;
    expect(within(row).getByText('schreibt')).toBeTruthy();
    expect(within(row).getAllByText('ACCT-ID').length).toBe(2);
  });

  it('wechselt über den Tab in die Netz-Ansicht', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    setup();
    await screen.findByText('INIT');
    fireEvent.click(screen.getByRole('tab', { name: 'Netz' }));
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Netz' }).getAttribute('aria-selected')).toBe('true'));
    expect(screen.queryByRole('table')).toBeNull();
  });
});
