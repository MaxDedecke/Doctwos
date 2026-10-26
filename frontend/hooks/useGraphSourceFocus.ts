import { useCallback, useRef, useState } from 'react';

/** Zustand der Quellen-Priorisierung der Graph-Übersicht; der Ref liest `loadOverview` ohne neue Abhängigkeit. */
export function useGraphSourceFocus() {
  const [focusSourceId, setFocusSourceId] = useState<number | null>(null);
  const focusRef = useRef<number | null>(null);

  const resetFocus = useCallback(() => {
    focusRef.current = null;
    queueMicrotask(() => setFocusSourceId(null));
  }, []);

  const changeFocus = useCallback((sourceId: number | null, reload: (force: boolean) => unknown) => {
    focusRef.current = sourceId;
    setFocusSourceId(sourceId);
    void reload(true);
  }, []);

  const addFocusParam = useCallback((params: URLSearchParams) => {
    if (focusRef.current !== null) params.set('focus_source_id', String(focusRef.current));
  }, []);

  return { focusSourceId, resetFocus, changeFocus, addFocusParam };
}
