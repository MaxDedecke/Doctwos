import type { FileReference, ProjectReferencesPage } from '@/types/domain';
import { useCallback, useRef, useState } from 'react';

/** Größe einer Seite im Referenzen-Menü und im Referenzen-Dialog. */
export const REFERENCE_PAGE_SIZE = 15;

export type ReferencePageFetcher = (offset: number, limit: number) => Promise<ProjectReferencesPage>;

/**
 * Seitenweise geladene Referenzliste: `load` startet eine neue Liste (erste Seite), `loadMore` hängt die
 * nächste Seite an. Antworten einer älteren Liste (z. B. nach einem Dateiwechsel) werden verworfen, und
 * paralleles Nachladen wird verhindert. Es wird nie automatisch nachgeladen.
 */
export function usePagedReferenceList() {
  const [items, setItems] = useState<FileReference[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const fetcherRef = useRef<ReferencePageFetcher | null>(null);
  const tokenRef = useRef(0);
  const loadedRef = useRef(0);
  const hasMoreRef = useRef(false);
  const loadingMoreRef = useRef(false);

  const clear = useCallback(() => {
    setItems([]);
    setTotal(0);
    setHasMore(false);
    hasMoreRef.current = false;
    loadedRef.current = 0;
  }, []);

  /** Verwirft die Liste, ohne etwas zu laden. */
  const reset = useCallback(() => {
    tokenRef.current += 1;
    fetcherRef.current = null;
    loadingMoreRef.current = false;
    setIsLoading(false);
    setIsLoadingMore(false);
    clear();
  }, [clear]);

  const load = useCallback(async (fetcher: ReferencePageFetcher) => {
    const token = ++tokenRef.current;
    fetcherRef.current = fetcher;
    loadingMoreRef.current = false;
    setIsLoadingMore(false);
    setIsLoading(true);
    try {
      const page = await fetcher(0, REFERENCE_PAGE_SIZE);
      if (token !== tokenRef.current) return;
      setItems(page.references);
      setTotal(page.total);
      setHasMore(page.has_more);
      hasMoreRef.current = page.has_more;
      loadedRef.current = page.references.length;
    } catch (error) {
      console.error('Failed to load references:', error);
      if (token === tokenRef.current) clear();
    } finally {
      if (token === tokenRef.current) setIsLoading(false);
    }
  }, [clear]);

  const loadMore = useCallback(async () => {
    const fetcher = fetcherRef.current;
    if (!fetcher || loadingMoreRef.current || !hasMoreRef.current) return;
    const token = tokenRef.current;
    loadingMoreRef.current = true;
    setIsLoadingMore(true);
    try {
      const page = await fetcher(loadedRef.current, REFERENCE_PAGE_SIZE);
      if (token !== tokenRef.current) return;
      setItems((previous) => [...previous, ...page.references]);
      setTotal(page.total);
      setHasMore(page.has_more);
      hasMoreRef.current = page.has_more;
      loadedRef.current += page.references.length;
    } catch (error) {
      console.error('Failed to load more references:', error);
      if (token === tokenRef.current) {
        setHasMore(false);
        hasMoreRef.current = false;
      }
    } finally {
      if (token === tokenRef.current) {
        loadingMoreRef.current = false;
        setIsLoadingMore(false);
      }
    }
  }, []);

  return { items, total, hasMore, isLoading, isLoadingMore, load, loadMore, reset };
}
