/**
 * O-036: der Chat-Verlauf wird gefenstert gerendert. jsdom liefert für jedes
 * Element offsetHeight=0 (kein echtes Layout) -- ohne einen festen Wert würde
 * der Virtualizer den Container als 0px hoch ansehen und gar keine Zeile
 * rendern. Für diese Tests wird `offsetHeight` daher global auf einen festen
 * Wert gemockt, damit sich ein realistisches, aber kleines Sichtfenster ergibt.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { VirtualizedSessionList, type SidebarSession } from './VirtualizedSessionList';

function makeSessions(count: number): SidebarSession[] {
  return Array.from({ length: count }, (_, i) => ({ id: i + 1, title: `Sitzung ${i + 1}` }));
}

describe('VirtualizedSessionList', () => {
  let offsetHeightSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    offsetHeightSpy = vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(150);
  });

  afterEach(() => {
    offsetHeightSpy.mockRestore();
  });

  it('renders only a windowed subset of a large session list, not all of them', () => {
    render(
      <VirtualizedSessionList
        sessions={makeSessions(500)}
        activeSessionId={null}
        theme="dark"
        onSelect={vi.fn()}
        onRemove={vi.fn()}
        deleteSessionTitle="Löschen"
      />
    );

    const renderedRows = screen.getAllByText(/^Sitzung \d+$/);
    expect(renderedRows.length).toBeGreaterThan(0);
    expect(renderedRows.length).toBeLessThan(500);
  });

  it('renders every session when the list is small', () => {
    render(
      <VirtualizedSessionList
        sessions={makeSessions(3)}
        activeSessionId={null}
        theme="dark"
        onSelect={vi.fn()}
        onRemove={vi.fn()}
        deleteSessionTitle="Löschen"
      />
    );

    expect(screen.getByText('Sitzung 1')).toBeTruthy();
    expect(screen.getByText('Sitzung 2')).toBeTruthy();
    expect(screen.getByText('Sitzung 3')).toBeTruthy();
  });

  it('calls onSelect with the clicked session', () => {
    const onSelect = vi.fn();
    const sessions = makeSessions(2);
    render(
      <VirtualizedSessionList
        sessions={sessions}
        activeSessionId={null}
        theme="dark"
        onSelect={onSelect}
        onRemove={vi.fn()}
        deleteSessionTitle="Löschen"
      />
    );

    fireEvent.click(document.getElementById('sidebar-session-item-1')!);

    expect(onSelect).toHaveBeenCalledWith(sessions[0]);
  });

  it('calls onRemove with the session id when the delete button is clicked', () => {
    const onRemove = vi.fn();
    render(
      <VirtualizedSessionList
        sessions={makeSessions(2)}
        activeSessionId={null}
        theme="dark"
        onSelect={vi.fn()}
        onRemove={onRemove}
        deleteSessionTitle="Löschen"
      />
    );

    fireEvent.click(document.getElementById('sidebar-remove-session-1')!);

    expect(onRemove).toHaveBeenCalledWith(1, expect.anything());
  });

  it('renders nothing for an empty session list', () => {
    render(
      <VirtualizedSessionList
        sessions={[]}
        activeSessionId={null}
        theme="dark"
        onSelect={vi.fn()}
        onRemove={vi.fn()}
        deleteSessionTitle="Löschen"
      />
    );

    expect(screen.queryByText(/^Sitzung/)).toBeNull();
  });
});
