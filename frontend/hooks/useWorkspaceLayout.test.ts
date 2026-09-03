/**
 * Regressionstests für O-029: der 3-Spalten-Layout-Modus bekommt zwei
 * ziehbare Teiler (analog zum bestehenden 2-Panel-Split und 4-grid-Kreuzgriff
 * aus O-021), statt starr zu gleichen Dritteln zu rendern.
 */
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useWorkspaceLayout } from './useWorkspaceLayout';
import { MIN_THREE_COL_PANEL_PERCENT } from '@/lib/workspaceResize';
import { api } from '@/app/services/api';

function fakeContainer(left: number, width: number): HTMLDivElement {
  return {
    getBoundingClientRect: () => ({ left, width, top: 0, height: 600, right: left + width, bottom: 600, x: left, y: 0, toJSON() {} }),
  } as unknown as HTMLDivElement;
}

function firePointerMove(clientX: number) {
  const event = new Event('pointermove') as unknown as PointerEvent;
  Object.assign(event, { clientX, clientY: 0 });
  window.dispatchEvent(event);
}

function firePointerUp() {
  window.dispatchEvent(new Event('pointerup'));
}

function renderLayout() {
  return renderHook(() => useWorkspaceLayout({
    activeSessionId: null,
    selectedProject: null,
    selectedSource: null,
    t: (key: string) => key,
  }));
}

describe('useWorkspaceLayout 3-col divider resize', () => {
  afterEach(() => {
    // Drags register their own window listeners inside the hook's effect;
    // stray pointerup safety net in case a test fails mid-drag.
    firePointerUp();
  });

  it('starts with the three columns split into even thirds', () => {
    const { result } = renderLayout();
    expect(result.current.threeColLeftPercent).toBeCloseTo(100 / 3);
    expect(result.current.threeColRightPercent).toBeCloseTo((100 / 3) * 2);
  });

  it('drags the left divider to reposition the panel 0/1 boundary', () => {
    const { result } = renderLayout();
    act(() => {
      result.current.splitContainerRef.current = fakeContainer(0, 1000);
    });

    act(() => {
      result.current.handleThreeColLeftDividerPointerDown({ preventDefault: () => {} } as React.PointerEvent);
    });
    expect(result.current.isDragging).toBe(true);

    act(() => {
      firePointerMove(400); // 40% of a 1000px-wide container
    });
    expect(result.current.threeColLeftPercent).toBeCloseTo(40);
    // The right boundary must not move while dragging the left one.
    expect(result.current.threeColRightPercent).toBeCloseTo((100 / 3) * 2);

    act(() => {
      firePointerUp();
    });
    expect(result.current.isDragging).toBe(false);
  });

  it('drags the right divider to reposition the panel 1/2 boundary', () => {
    const { result } = renderLayout();
    act(() => {
      result.current.splitContainerRef.current = fakeContainer(0, 1000);
    });

    act(() => {
      result.current.handleThreeColRightDividerPointerDown({ preventDefault: () => {} } as React.PointerEvent);
    });

    act(() => {
      firePointerMove(850); // 85% of a 1000px-wide container
    });
    expect(result.current.threeColRightPercent).toBeCloseTo(85);
    expect(result.current.threeColLeftPercent).toBeCloseTo(100 / 3);
  });

  it('keeps the dragged divider from crossing the other one below the minimum column width', () => {
    const { result } = renderLayout();
    act(() => {
      result.current.splitContainerRef.current = fakeContainer(0, 1000);
    });

    // Right boundary sits at its default (~66.67%); dragging the left divider
    // far past it must clamp to (right - MIN_THREE_COL_PANEL_PERCENT), not
    // overshoot into (or past) panel 1's territory.
    act(() => {
      result.current.handleThreeColLeftDividerPointerDown({ preventDefault: () => {} } as React.PointerEvent);
    });
    act(() => {
      firePointerMove(950); // 95% -- far beyond the right divider
    });

    const expectedMax = (100 / 3) * 2 - MIN_THREE_COL_PANEL_PERCENT;
    expect(result.current.threeColLeftPercent).toBeCloseTo(expectedMax);

    act(() => {
      firePointerUp();
    });
  });

  it('never lets a dragged divider shrink a column below MIN_THREE_COL_PANEL_PERCENT at the container edge', () => {
    const { result } = renderLayout();
    act(() => {
      result.current.splitContainerRef.current = fakeContainer(0, 1000);
    });

    act(() => {
      result.current.handleThreeColRightDividerPointerDown({ preventDefault: () => {} } as React.PointerEvent);
    });
    act(() => {
      firePointerMove(999); // pointer dragged to the far right edge
    });

    expect(result.current.threeColRightPercent).toBeCloseTo(100 - MIN_THREE_COL_PANEL_PERCENT);

    act(() => {
      firePointerUp();
    });
  });

  it('resets the three-column boundaries back to even thirds', () => {
    const { result } = renderLayout();
    act(() => {
      result.current.splitContainerRef.current = fakeContainer(0, 1000);
    });
    act(() => {
      result.current.handleThreeColLeftDividerPointerDown({ preventDefault: () => {} } as React.PointerEvent);
    });
    act(() => {
      firePointerMove(400);
    });
    act(() => {
      firePointerUp();
    });
    expect(result.current.threeColLeftPercent).toBeCloseTo(40);

    act(() => {
      result.current.resetWorkspace();
    });
    expect(result.current.threeColLeftPercent).toBeCloseTo(100 / 3);
    expect(result.current.threeColRightPercent).toBeCloseTo((100 / 3) * 2);
  });
});

/**
 * Regressionstests für den O-038-Folgefix: die debounced Snapshot-Autosave
 * aktualisiert nach einem erfolgreichen PATCH .../snapshot jetzt auch den
 * lokal gecachten Sitzungs-Eintrag -- vorher blieb `snapshot_json` im
 * Sidebar-Cache dauerhaft veraltet (oder null), weil nur die DB geschrieben
 * wurde. Erneutes Anklicken derselben Sitzung (ohne Reload) stellte dadurch
 * einen falschen oder leeren Panel-Zustand wieder her.
 */
describe('useWorkspaceLayout snapshot autosave cache sync', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('patches the matching cached session entry with the freshly saved snapshot once the debounce fires', async () => {
    vi.useFakeTimers();
    const updateSnapshotSpy = vi.spyOn(api, 'updateChatSessionSnapshot').mockResolvedValue({} as any);
    const setSessions = vi.fn();

    const { rerender } = renderHook(
      (props: { activeSessionId: number | null }) => useWorkspaceLayout({
        activeSessionId: props.activeSessionId,
        selectedProject: null,
        selectedSource: null,
        t: (key: string) => key,
        setSessions,
      }),
      { initialProps: { activeSessionId: null as number | null } }
    );

    // Activating a session is what starts the debounce (see the effect's
    // dependency array in useWorkspaceLayout.ts) -- mirrors what page.tsx
    // does when a session is created or selected.
    rerender({ activeSessionId: 55 });

    await act(async () => {
      vi.advanceTimersByTime(1300);
      // Flush the microtask queue so the mocked (already-resolved) API
      // promise's .then() callback actually runs before we assert on it.
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(updateSnapshotSpy).toHaveBeenCalledTimes(1);
    const [savedSessionId, savedSnapshot] = updateSnapshotSpy.mock.calls[0];
    expect(savedSessionId).toBe(55);

    expect(setSessions).toHaveBeenCalledTimes(1);
    const cacheUpdater = setSessions.mock.calls[0][0];
    expect(cacheUpdater([
      { id: 55, snapshot_json: null },
      { id: 9, snapshot_json: { panelConfigs: ['chat'] } },
    ])).toEqual([
      { id: 55, snapshot_json: savedSnapshot },
      { id: 9, snapshot_json: { panelConfigs: ['chat'] } },
    ]);
  });

  it('does not touch the session cache when no setSessions was provided', async () => {
    vi.useFakeTimers();
    vi.spyOn(api, 'updateChatSessionSnapshot').mockResolvedValue({} as any);

    const { rerender } = renderHook(
      (props: { activeSessionId: number | null }) => useWorkspaceLayout({
        activeSessionId: props.activeSessionId,
        selectedProject: null,
        selectedSource: null,
        t: (key: string) => key,
      }),
      { initialProps: { activeSessionId: null as number | null } }
    );

    rerender({ activeSessionId: 55 });

    // Must not throw despite setSessions being undefined.
    await act(async () => {
      vi.advanceTimersByTime(1300);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(api.updateChatSessionSnapshot).toHaveBeenCalledTimes(1);
  });
});
