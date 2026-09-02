import { useCallback, useEffect, useState } from 'react';

const DEFAULT_THEME = 'dark';
const DEFAULT_EDITOR_FONT_SIZE = 13;
const DEFAULT_EDITOR_MINIMAP = true;
const DEFAULT_EDITOR_FONT_FAMILY = "'JetBrains Mono', monospace";

function readEditorFontSize(): number {
  const stored = Number(localStorage.getItem('doctus-editor-font-size'));
  return [12, 13, 14, 15, 16, 18].includes(stored) ? stored : DEFAULT_EDITOR_FONT_SIZE;
}

function readEditorMinimap(): boolean {
  const stored = localStorage.getItem('doctus-editor-minimap');
  return stored === null ? DEFAULT_EDITOR_MINIMAP : stored === 'true';
}

function readEditorFontFamily(): string {
  const stored = localStorage.getItem('doctus-editor-font-family');
  return stored === "'Fira Code', monospace" || stored === 'monospace'
    ? stored
    : DEFAULT_EDITOR_FONT_FAMILY;
}

/** Owns browser-persisted visual settings shared by the shell and settings UI. */
export function useDisplaySettings() {
  const [theme, setThemeState] = useState(DEFAULT_THEME);
  const [editorFontSize, setEditorFontSizeState] = useState(DEFAULT_EDITOR_FONT_SIZE);
  const [editorMinimap, setEditorMinimapState] = useState(DEFAULT_EDITOR_MINIMAP);
  const [editorFontFamily, setEditorFontFamilyState] = useState(DEFAULT_EDITOR_FONT_FAMILY);

  useEffect(() => {
    const storedTheme = localStorage.getItem('doctus-theme');
    // Restore browser preferences after the deterministic server/default
    // render; otherwise a persisted light theme would break hydration.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (storedTheme === 'light' || storedTheme === 'dark') setThemeState(storedTheme);
    setEditorFontSizeState(readEditorFontSize());
    setEditorMinimapState(readEditorMinimap());
    setEditorFontFamilyState(readEditorFontFamily());
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  const setTheme = useCallback((nextTheme: string) => {
    setThemeState(nextTheme);
    localStorage.setItem('doctus-theme', nextTheme);
  }, []);

  const setEditorFontSize = useCallback((size: number) => {
    setEditorFontSizeState(size);
    localStorage.setItem('doctus-editor-font-size', String(size));
  }, []);

  const setEditorMinimap = useCallback((show: boolean) => {
    setEditorMinimapState(show);
    localStorage.setItem('doctus-editor-minimap', String(show));
  }, []);

  const setEditorFontFamily = useCallback((family: string) => {
    setEditorFontFamilyState(family);
    localStorage.setItem('doctus-editor-font-family', family);
  }, []);

  return {
    theme,
    setTheme,
    editorFontSize,
    setEditorFontSize,
    editorMinimap,
    setEditorMinimap,
    editorFontFamily,
    setEditorFontFamily,
  };
}
