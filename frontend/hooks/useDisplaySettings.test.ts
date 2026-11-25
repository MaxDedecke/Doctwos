import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { useDisplaySettings } from './useDisplaySettings';

describe('useDisplaySettings', () => {
  beforeEach(() => {
    localStorage.clear();
    document.cookie = 'codena-theme=; Max-Age=0; Path=/';
  });

  it('restores and persists the visual editor preferences', async () => {
    localStorage.setItem('codena-theme', 'light');
    localStorage.setItem('codena-editor-font-size', '16');
    localStorage.setItem('codena-editor-minimap', 'false');
    localStorage.setItem('codena-editor-font-family', 'monospace');

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

    expect(localStorage.getItem('codena-theme')).toBe('dark');
    expect(document.cookie).toContain('codena-theme=dark');
    expect(localStorage.getItem('codena-editor-font-size')).toBe('18');
    expect(localStorage.getItem('codena-editor-minimap')).toBe('true');
    expect(localStorage.getItem('codena-editor-font-family')).toBe("'Fira Code', monospace");
  });

  it('prefers the theme cookie so the unauthenticated page can use it', async () => {
    localStorage.setItem('codena-theme', 'light');
    document.cookie = 'codena-theme=dark; Path=/';

    const { result } = renderHook(() => useDisplaySettings());

    await waitFor(() => expect(result.current.theme).toBe('dark'));
  });
});
