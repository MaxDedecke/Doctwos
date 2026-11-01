import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { api } from '@/app/services/api';
import { DropView } from './DropView';

const node = (id: number, name: string, layer: number) => ({ id, name, type: 'method', role: 'routine', source_id: 8, file_path: `src/${name}.java`, start_line: 10, cite: `src/${name}.java:10`, layer });
const RESULT = {
  root: node(1, 'create', 0), direction: 'down', kinds: ['control'], stopped: 'end', collapse_above: 40,
  layers: [
    { layer: 0, count: 1, unresolved: 0, nodes: [node(1, 'create', 0)], edges: [] },
    { layer: 1, count: 2, unresolved: 3, nodes: [node(2, 'doCreate', 1), node(3, 'audit', 1)], edges: [] },
  ],
};

function renderView(onFileSelect = vi.fn()) {
  render(<LanguageProvider><DropView theme="dark" focusedEntity={{ id: 1, name: 'create' }} projectId={2} onFileSelect={onFileSelect} /></LanguageProvider>);
  return onFileSelect;
}

const view = (focus: { id: number; name: string } | null, extra: Partial<React.ComponentProps<typeof DropView>> = {}) => (
  <LanguageProvider><DropView theme="dark" focusedEntity={focus} projectId={2} onFileSelect={vi.fn()} {...extra} /></LanguageProvider>
);
const CHAT_FLOW = {
  root: { id: 1, name: 'MAIN', type: 'program', file_path: 'MAIN.cbl', start_line: 1, source_id: 7 },
  hops: 2, direction: 'outgoing' as const, truncated: true,
  nodes: [
    { id: 1, name: 'MAIN', type: 'program', file_path: 'MAIN.cbl', start_line: 1, source_id: 7 },
    { id: 2, name: 'STEP', type: 'paragraph', file_path: 'MAIN.cbl', start_line: 20, source_id: 7, analysis_status: 'partial' as const },
  ],
  edges: [
    { id: 10, source: 1, target: 2, target_name: 'STEP', type: 'PERFORM', resolution: 'resolved', start_line: 5, meta: { resolution_reason: 'Paragraph im selben Programm' } },
    { id: 11, source: 2, target: null, target_name: 'UNBEKANNT', type: 'CALL', resolution: 'unresolved', start_line: 25 },
  ],
  focus_entity_id: 2,
  highlighted_edge_id: 10,
};

describe('DropView', () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it('keeps its settings when the focus changes and follows the new start point', async () => {
    const spy = vi.spyOn(api, 'getEntityDrop').mockResolvedValue({ data: RESULT } as never);
    const { rerender } = render(view({ id: 1, name: 'create' }));
    await screen.findByTestId('drop-node-2');
    fireEvent.click(screen.getByRole('button', { name: /Aufwärts zeigen/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Daten' }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(1, expect.objectContaining({ direction: 'up', kinds: ['control', 'data'] })));

    rerender(view({ id: 9, name: 'other' }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(9, expect.objectContaining({ direction: 'up', kinds: ['control', 'data'] })));

    // Fokus aufgehoben: Der Stand bleibt, nichts wird neu geladen.
    const calls = spy.mock.calls.length;
    rerender(view(null));
    expect(spy.mock.calls.length).toBe(calls);
    expect(screen.getByTestId('drop-pyramid')).toBeTruthy();
  });

  it('goes back to the previous start point', async () => {
    const spy = vi.spyOn(api, 'getEntityDrop').mockResolvedValue({ data: RESULT } as never);
    renderView();
    await screen.findByTestId('drop-node-2');
    expect(screen.queryByRole('button', { name: /Zurück zu/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /doCreate als neuen Startpunkt/ }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(2, expect.anything()));
    fireEvent.click(await screen.findByRole('button', { name: 'Zurück zu create' }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(1, expect.anything()));
    expect(screen.queryByRole('button', { name: /Zurück zu/ })).toBeNull();
  });

  it('marks edges leading back and shows the details of a clicked connection', async () => {
    const edge = { from: 3, to: 2, type: 'PERFORM', resolution: 'resolved', cite: 'src/audit.java:44', condition: 'WS-A = 1', reason: 'Name eindeutig', provenance: undefined };
    const data = { ...RESULT, back_edges: [edge] };
    vi.spyOn(api, 'getEntityDrop').mockResolvedValue({ data } as never);
    const onFileSelect = renderView();
    await screen.findByTestId('drop-node-2');
    const key = '3>2:PERFORM';
    await waitFor(() => expect(document.querySelector(`[data-edge="${key}"]`)?.getAttribute('data-back')).toBe('true'));
    expect(screen.getByText(/Gestrichelt/)).toBeTruthy();

    fireEvent.click(document.querySelector(`[data-edge-hit="${key}"]`) as Element);
    const details = screen.getByTestId('drop-edge-details');
    expect(details.textContent).toContain('WS-A = 1');
    expect(details.textContent).toContain('Name eindeutig');
    expect(details.textContent).toContain('src/audit.java:44');
    fireEvent.click(screen.getByRole('button', { name: 'Fundstelle öffnen' }));
    expect(onFileSelect).toHaveBeenCalledWith('src/audit.java', 44, 8);
    fireEvent.click(screen.getByRole('button', { name: 'Details schließen' }));
    expect(screen.queryByTestId('drop-edge-details')).toBeNull();
  });

  it('shows a chat flow as layers without loading, with its focus, marked edge and open targets', async () => {
    const spy = vi.spyOn(api, 'getEntityDrop');
    const onClear = vi.fn();
    render(view({ id: 1, name: 'MAIN' }, { customFlow: CHAT_FLOW, onClearCustomFlow: onClear }));
    await screen.findByTestId('drop-node-2');
    expect(spy).not.toHaveBeenCalled();
    expect(screen.getByTestId('drop-flow-banner').textContent).toContain('Ablauf');
    expect(screen.getByText(/Gekürzt/)).toBeTruthy();
    expect(screen.getByTestId('drop-node-2').className).toContain('ring-2');
    expect(screen.getByTestId('drop-node-status-2')).toBeTruthy();
    await waitFor(() => expect(document.querySelector('[data-edge="1>2:PERFORM"]')?.getAttribute('data-marked')).toBe('true'));
    // Offenes Ziel: Knoten ja, aber ohne Quelle zum Öffnen.
    expect(screen.getByText('UNBEKANNT')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Quellcode von UNBEKANNT/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /als neuen Startpunkt/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Aufwärts zeigen/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Fokusansicht laden' }));
    expect(onClear).toHaveBeenCalled();
  });

  it('keeps an impact graph inside its result', async () => {
    render(view({ id: 1, name: 'MAIN' }, { customFlow: { ...CHAT_FLOW, mode: 'impact' } }));
    await screen.findByTestId('drop-node-2');
    expect(screen.getByTestId('drop-flow-banner').textContent).toContain('Betroffenengraph');
    expect(screen.queryByRole('button', { name: /Quellcode von STEP/ })).toBeNull();
    expect(document.querySelector('[data-edge-hit]')).toBeNull();
  });

  it('shows the start point on top and the layers below, opens a node at its line', async () => {
    const spy = vi.spyOn(api, 'getEntityDrop').mockResolvedValue({ data: RESULT } as never);
    const onFileSelect = renderView();
    await screen.findByTestId('drop-node-2');
    expect(spy).toHaveBeenCalledWith(1, expect.objectContaining({ direction: 'down', layers: 3, kinds: ['control'], expand: [] }));
    expect(screen.getByTestId('drop-layer-0')).toBeTruthy();
    // Die Verbindungen zwischen den Ebenen liegen als SVG-Ebene hinter den Knoten.
    expect(screen.getByTestId('drop-connectors').tagName.toLowerCase()).toBe('svg');
    expect(screen.getByText(/3 nicht aufgelöst/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Quellcode von doCreate/ }));
    expect(onFileSelect).toHaveBeenCalledWith('src/doCreate.java', 10, 8);
  });

  it('switches between layers below and beside each other and remembers it, without loading again', async () => {
    window.localStorage.removeItem('doctus-drop-orientation');
    const spy = vi.spyOn(api, 'getEntityDrop').mockResolvedValue({ data: RESULT } as never);
    renderView();
    const pyramid = await screen.findByTestId('drop-pyramid');
    expect(pyramid.getAttribute('data-orientation')).toBe('vertical');
    const calls = spy.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: 'Ebenen nebeneinander anzeigen' }));
    expect(screen.getByTestId('drop-pyramid').getAttribute('data-orientation')).toBe('horizontal');
    expect(window.localStorage.getItem('doctus-drop-orientation')).toBe('horizontal');
    expect(spy.mock.calls.length).toBe(calls);

    fireEvent.click(screen.getByRole('button', { name: 'Ebenen untereinander anzeigen' }));
    expect(screen.getByTestId('drop-pyramid').getAttribute('data-orientation')).toBe('vertical');
  });

  it('loads the other direction and further kinds only when switched', async () => {
    const spy = vi.spyOn(api, 'getEntityDrop').mockResolvedValue({ data: RESULT } as never);
    renderView();
    await screen.findByTestId('drop-node-2');
    expect(spy).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: /Aufwärts zeigen/ }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(1, expect.objectContaining({ direction: 'up' })));
    fireEvent.click(screen.getByRole('button', { name: 'Daten' }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(1, expect.objectContaining({ kinds: ['control', 'data'] })));
  });

  it('zooms with the icons, resets to 100 percent and keeps the zoom without loading again', async () => {
    const spy = vi.spyOn(api, 'getEntityDrop').mockResolvedValue({ data: RESULT } as never);
    const { rerender } = render(view({ id: 1, name: 'create' }));
    await screen.findByTestId('drop-node-2');
    const calls = spy.mock.calls.length;
    const zoomOf = () => screen.getByTestId('drop-pyramid').style.zoom;
    expect(zoomOf()).toBe('1');

    fireEvent.click(screen.getByRole('button', { name: 'Verkleinern' }));
    expect(zoomOf()).toBe('0.8');
    fireEvent.click(screen.getByRole('button', { name: 'Vergrößern' }));
    fireEvent.click(screen.getByRole('button', { name: 'Vergrößern' }));
    expect(zoomOf()).toBe('1.25');
    expect(screen.getByRole('button', { name: 'Zoom auf 100 % zurücksetzen' }).textContent).toBe('125%');
    fireEvent.click(screen.getByRole('button', { name: 'Zoom auf 100 % zurücksetzen' }));
    expect(zoomOf()).toBe('1');
    expect(spy.mock.calls.length).toBe(calls);

    // Wie die übrigen Einstellungen übersteht der Zoom einen Fokuswechsel.
    fireEvent.click(screen.getByRole('button', { name: 'Verkleinern' }));
    rerender(view({ id: 9, name: 'other' }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(9, expect.anything()));
    expect(zoomOf()).toBe('0.8');
  });

  it('stops at the smallest level', async () => {
    vi.spyOn(api, 'getEntityDrop').mockResolvedValue({ data: RESULT } as never);
    renderView();
    await screen.findByTestId('drop-node-2');
    const out = screen.getByRole('button', { name: 'Verkleinern' }) as HTMLButtonElement;
    for (let step = 0; step < 6; step += 1) fireEvent.click(out);
    expect(screen.getByTestId('drop-pyramid').style.zoom).toBe('0.25');
    expect(out.disabled).toBe(true);
  });

  it('keeps a collapsed layer closed until the user expands it', async () => {
    const collapsed = { ...RESULT, stopped: 'collapsed', layers: [RESULT.layers[0], { layer: 1, count: 91, unresolved: 0, nodes: [], edges: [], collapsed: true }] };
    const spy = vi.spyOn(api, 'getEntityDrop').mockResolvedValue({ data: collapsed } as never);
    renderView();
    fireEvent.click(await screen.findByRole('button', { name: /91 Knoten anzeigen/ }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(1, expect.objectContaining({ expand: [1] })));
  });
});
