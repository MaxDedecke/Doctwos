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

describe('DropView', () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it('shows the start point on top and the layers below, opens a node at its line', async () => {
    const spy = vi.spyOn(api, 'getEntityDrop').mockResolvedValue({ data: RESULT } as never);
    const onFileSelect = renderView();
    await screen.findByTestId('drop-node-2');
    expect(spy).toHaveBeenCalledWith(1, expect.objectContaining({ direction: 'down', layers: 3, kinds: ['control'], expand: [] }));
    expect(screen.getByTestId('drop-layer-0')).toBeTruthy();
    // Die Verbindungen zwischen den Ebenen liegen als SVG-Ebene hinter den Knoten.
    expect(screen.getByTestId('drop-connectors').tagName.toLowerCase()).toBe('svg');
    expect(screen.getByText(/3 nicht aufgelöst/)).toBeTruthy();
    fireEvent.click(screen.getByText('doCreate'));
    expect(onFileSelect).toHaveBeenCalledWith('src/doCreate.java', 10, 8);
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

  it('keeps a collapsed layer closed until the user expands it', async () => {
    const collapsed = { ...RESULT, stopped: 'collapsed', layers: [RESULT.layers[0], { layer: 1, count: 91, unresolved: 0, nodes: [], edges: [], collapsed: true }] };
    const spy = vi.spyOn(api, 'getEntityDrop').mockResolvedValue({ data: collapsed } as never);
    renderView();
    fireEvent.click(await screen.findByRole('button', { name: /91 Knoten anzeigen/ }));
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(1, expect.objectContaining({ expand: [1] })));
  });
});
