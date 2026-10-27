import { act, renderHook, waitFor } from '@testing-library/react';
import { expect, it } from 'vitest';
import { useGraphStyleRevision } from './useGraphStyleRevision';

it('invalidates a cached palette after the root theme or inline tokens change', async () => {
  const root = document.documentElement;
  const originalClass = root.className, originalStyle = root.style.cssText;
  const { result, unmount } = renderHook(() => useGraphStyleRevision());
  try {
    const first = result.current;
    act(() => root.classList.toggle('dark'));
    await waitFor(() => expect(result.current).not.toBe(first));
    const second = result.current;
    act(() => root.style.setProperty('--ds-accent', '1 2 3'));
    await waitFor(() => expect(result.current).not.toBe(second));
  } finally {
    unmount();
    root.className = originalClass;
    root.style.cssText = originalStyle;
  }
});
