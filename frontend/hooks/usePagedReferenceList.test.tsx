import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FileReference, ProjectReferencesPage } from '@/types/domain';
import { REFERENCE_PAGE_SIZE, usePagedReferenceList } from './usePagedReferenceList';

const refs = (from: number, count: number): FileReference[] =>
  Array.from({ length: count }, (_, i) => ({ id: from + i, title: `Ref ${from + i}`, file_path: `f${from + i}.cbl` }));
const page = (references: FileReference[], total: number, offset: number): ProjectReferencesPage => ({
  references, total, has_more: offset + references.length < total, offset, limit: REFERENCE_PAGE_SIZE,
});
/** Fetcher über eine Liste mit `total` Einträgen. */
const fetcherFor = (total: number) => vi.fn(async (offset: number, limit: number) =>
  page(refs(offset, Math.min(limit, Math.max(0, total - offset))), total, offset));

describe('usePagedReferenceList', () => {
  it('loads only the first page of 15 and reports the total and whether more exist', async () => {
    const fetcher = fetcherFor(40);
    const { result } = renderHook(() => usePagedReferenceList());

    await act(async () => { await result.current.load(fetcher); });

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledWith(0, 15);
    expect(result.current.items).toHaveLength(15);
    expect(result.current.total).toBe(40);
    expect(result.current.hasMore).toBe(true);
  });

  it('appends the next pages only on demand until the list is complete', async () => {
    const fetcher = fetcherFor(40);
    const { result } = renderHook(() => usePagedReferenceList());
    await act(async () => { await result.current.load(fetcher); });

    await act(async () => { await result.current.loadMore(); });
    expect(fetcher).toHaveBeenLastCalledWith(15, 15);
    expect(result.current.items).toHaveLength(30);
    expect(result.current.hasMore).toBe(true);

    await act(async () => { await result.current.loadMore(); });
    expect(fetcher).toHaveBeenLastCalledWith(30, 15);
    expect(result.current.items).toHaveLength(40);
    expect(result.current.hasMore).toBe(false);

    await act(async () => { await result.current.loadMore(); });
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it('does not start a second request while one page is loading', async () => {
    let resolveMore: (value: ProjectReferencesPage) => void = () => {};
    const fetcher = vi.fn()
      .mockResolvedValueOnce(page(refs(0, 15), 40, 0))
      .mockReturnValueOnce(new Promise((resolve) => { resolveMore = resolve; }));
    const { result } = renderHook(() => usePagedReferenceList());
    await act(async () => { await result.current.load(fetcher); });

    act(() => { void result.current.loadMore(); void result.current.loadMore(); });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(result.current.isLoadingMore).toBe(true);

    await act(async () => { resolveMore(page(refs(15, 15), 40, 15)); });
    await waitFor(() => expect(result.current.items).toHaveLength(30));
    expect(result.current.isLoadingMore).toBe(false);
  });

  it('drops a late page of an earlier list after a new list was started', async () => {
    let resolveMore: (value: ProjectReferencesPage) => void = () => {};
    const first = vi.fn()
      .mockResolvedValueOnce(page(refs(0, 15), 40, 0))
      .mockReturnValueOnce(new Promise((resolve) => { resolveMore = resolve; }));
    const second = fetcherFor(3);
    const { result } = renderHook(() => usePagedReferenceList());
    await act(async () => { await result.current.load(first); });
    act(() => { void result.current.loadMore(); });

    await act(async () => { await result.current.load(second); });
    await act(async () => { resolveMore(page(refs(15, 15), 40, 15)); });

    expect(result.current.items.map((item) => item.id)).toEqual([0, 1, 2]);
    expect(result.current.total).toBe(3);
    expect(result.current.hasMore).toBe(false);
  });

  it('stops offering more after a failed page and empties the list when the first page fails', async () => {
    const failing = vi.fn()
      .mockResolvedValueOnce(page(refs(0, 15), 40, 0))
      .mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => usePagedReferenceList());
    await act(async () => { await result.current.load(failing); });
    await act(async () => { await result.current.loadMore(); });
    expect(result.current.hasMore).toBe(false);
    expect(result.current.items).toHaveLength(15);

    const broken = vi.fn().mockRejectedValue(new Error('down'));
    await act(async () => { await result.current.load(broken); });
    expect(result.current.items).toEqual([]);
    expect(result.current.isLoading).toBe(false);
  });

  it('reset empties the list and ignores answers that were still on the way', async () => {
    let resolveFirst: (value: ProjectReferencesPage) => void = () => {};
    const fetcher = vi.fn().mockReturnValue(new Promise((resolve) => { resolveFirst = resolve; }));
    const { result } = renderHook(() => usePagedReferenceList());
    act(() => { void result.current.load(fetcher); });

    act(() => { result.current.reset(); });
    await act(async () => { resolveFirst(page(refs(0, 15), 40, 0)); });

    expect(result.current.items).toEqual([]);
    expect(result.current.isLoading).toBe(false);
  });
});
