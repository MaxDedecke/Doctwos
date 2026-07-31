'use client';

import React, { createContext, useContext, useState, useCallback, useMemo, useSyncExternalStore } from 'react';
import de from './de.json';
import en from './en.json';

export type Language = 'de' | 'en';

const DICTIONARIES: Record<Language, any> = { de, en };
const STORAGE_KEY = 'doctus-language';

function resolveKey(dict: any, key: string): string | undefined {
  let node = dict;
  for (const part of key.split('.')) {
    if (node == null) return undefined;
    node = node[part];
  }
  return typeof node === 'string' ? node : undefined;
}

interface LanguageContextValue {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const LanguageContext = createContext<LanguageContextValue | undefined>(undefined);

const noopSubscribe = () => () => {};

function getStoredLanguage(): Language {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === 'de' || stored === 'en' ? stored : 'de';
}

function getServerLanguage(): Language {
  return 'de';
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  // SSR and the first client render both need to agree on 'de' to avoid a
  // hydration mismatch, so a persisted 'en' can only become visible on the
  // render pass right after mount — useSyncExternalStore gives us that
  // without a setState-in-effect. User-driven changes are tracked
  // separately since they must win over whatever is in storage.
  const storedLanguage = useSyncExternalStore(noopSubscribe, getStoredLanguage, getServerLanguage);
  const [override, setOverride] = useState<Language | null>(null);
  const language = override ?? storedLanguage;

  const setLanguage = useCallback((lang: Language) => {
    setOverride(lang);
    window.localStorage.setItem(STORAGE_KEY, lang);
  }, []);

  const t = useCallback((key: string, vars?: Record<string, string | number>) => {
    const value = resolveKey(DICTIONARIES[language], key) ?? resolveKey(DICTIONARIES.de, key) ?? key;
    if (!vars) return value;
    return Object.entries(vars).reduce(
      (acc, [varName, varValue]) => acc.replace(`{{${varName}}}`, String(varValue)),
      value
    );
  }, [language]);

  const value = useMemo(() => ({ language, setLanguage, t }), [language, setLanguage, t]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLanguage must be used within a LanguageProvider');
  return ctx;
}
