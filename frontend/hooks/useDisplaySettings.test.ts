import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { useDisplaySettings } from './useDisplaySettings';

describe('useDisplaySettings', () => {
  beforeEach(() => localStorage.clear());

  it('restores and persists the visual editor preferences', async () => {
    localStorage.setItem('doctus-theme', 'light');
    localStorage.setItem('doctus-editor-font-size', '16');
    localStorage.setItem('doctus-editor-minimap', 'false');
    localStorage.setItem('doctus-editor-font-family', 'monospace');

    const { result } = renderHook(() => useDisplaySettings());

    await waitFor(() => expect(result.current.theme).toBe('light'));
    expect(result.current.editorFontSize).toBe(16);
    expect(result.current.editorMinimap).toBe(false);
    expect(result.current.editorFontFamily).toBe('monospace');

    act(() => {
      result.current.setTheme('dark');
      result.current.setEditorFontSize(18);
      result.current.setEditorMinimap(true);
      result.current.setEditorFontFamily("'Fira Code', monospace");
    });

    expect(localStorage.getItem('doctus-theme')).toBe('dark');
    expect(localStorage.getItem('doctus-editor-font-size')).toBe('18');
    expect(localStorage.getItem('doctus-editor-minimap')).toBe('true');
    expect(localStorage.getItem('doctus-editor-font-family')).toBe("'Fira Code', monospace");
  });
});
