import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FLOW_STEP_MS, useFlowAnimation } from './useFlowAnimation';

const endpoints = new Map([
  ['a', { source: 'r', target: 'x' }], ['b', { source: 'x', target: 'y' }], ['c', { source: 'r', target: 'z' }],
]);
const paths = [['a', 'b'], ['c']];

function mockMotion(reduce: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: reduce && query.includes('reduce'), media: query,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

describe('useFlowAnimation', () => {
  beforeEach(() => { vi.useFakeTimers(); mockMotion(false); });
  afterEach(() => { vi.useRealTimers(); });

  it('ist standardmäßig aus und zeigt dann nichts hervor', () => {
    const { result } = renderHook(() => useFlowAnimation(paths, endpoints, 'r'));
    expect(result.current.active).toBe(false);
    expect(result.current.view.activeEdgeId).toBeNull();
  });

  it('läuft nach dem Einschalten Takt für Takt in Dauerschleife über alle Pfade', () => {
    const { result } = renderHook(() => useFlowAnimation(paths, endpoints, 'r'));
    act(() => result.current.toggle());
    const edges: Array<string | null> = [];
    for (let i = 0; i < 7; i += 1) {
      act(() => { vi.advanceTimersByTime(FLOW_STEP_MS); });
      edges.push(result.current.view.activeEdgeId);
    }
    // Pfad 1: a, b | Takt nur mit der Wurzel (null) | Pfad 2: c | Wurzeltakt | wieder Pfad 1 …
    expect(edges).toEqual(['a', 'b', null, 'c', null, 'a', 'b']);
  });

  it('pausiert, ändert das Tempo und bleibt bei einem gewählten Pfad', () => {
    const { result } = renderHook(() => useFlowAnimation(paths, endpoints, 'r'));
    act(() => result.current.toggle());
    act(() => result.current.togglePause());
    act(() => { vi.advanceTimersByTime(FLOW_STEP_MS * 3); });
    expect(result.current.view.activeEdgeId).toBeNull();

    act(() => result.current.togglePause());
    act(() => result.current.cycleSpeed());
    expect(result.current.speed).toBe(2);
    act(() => { vi.advanceTimersByTime(FLOW_STEP_MS / 2); });
    expect(result.current.view.activeEdgeId).toBe('a');

    act(() => result.current.selectPath(1));
    for (let i = 0; i < 6; i += 1) act(() => { vi.advanceTimersByTime(FLOW_STEP_MS / 2); });
    expect(result.current.cursor.path).toBe(1);
  });

  it('bleibt mit prefers-reduced-motion oder ohne Pfade aus', () => {
    mockMotion(true);
    const reduced = renderHook(() => useFlowAnimation(paths, endpoints, 'r'));
    act(() => reduced.result.current.toggle());
    expect(reduced.result.current.supported).toBe(false);
    expect(reduced.result.current.active).toBe(false);

    mockMotion(false);
    const empty = renderHook(() => useFlowAnimation([], endpoints, 'r'));
    expect(empty.result.current.supported).toBe(false);
  });

  it('setzt bei neuen Pfaden zurück', () => {
    const { result, rerender } = renderHook(({ p }) => useFlowAnimation(p, endpoints, 'r'), { initialProps: { p: paths } });
    act(() => result.current.toggle());
    act(() => { vi.advanceTimersByTime(FLOW_STEP_MS * 2); });
    expect(result.current.cursor.step).toBe(2);
    rerender({ p: [['c']] });
    expect(result.current.cursor).toEqual({ path: 0, step: 0 });
  });
});
