import { useCallback, useEffect, useState } from 'react';

const DEFAULT_THEME = 'dark';
const DEFAULT_EDITOR_FONT_SIZE = 13;
const DEFAULT_EDITOR_MINIMAP = true;
const DEFAULT_EDITOR_FONT_FAMILY = "'JetBrains Mono', monospace";
const THEME_COOKIE = 'doctus-theme';
const THEME_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

function readThemeCookie(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)doctus-theme=(light|dark)(?:;|$)/);
  return match?.[1] ?? null;
}

function readStoredTheme(): string | null {
  // The cookie is canonical because it is available before authentication and
  // can therefore also theme the login page on its first paint. The old
  // localStorage value remains a one-time-compatible fallback for existing users.
  return readThemeCookie() || localStorage.getItem(THEME_COOKIE);
}

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
    const storedTheme = readStoredTheme();
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
    document.cookie = `${THEME_COOKIE}=${nextTheme}; Path=/; Max-Age=${THEME_COOKIE_MAX_AGE}; SameSite=Lax`;
    // Keep the legacy key in sync so older open tabs and deployments migrate
    // without losing the user's preference.
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
