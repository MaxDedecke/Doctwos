import { api } from '@/app/services/api';
import type { SearchResult } from '@/types/domain';
import { useEffect, useState } from 'react';

const MENTION_RE = /(^|\s)@([\w.$#-]{2,60})$/;
const DEBOUNCE_MS = 200;

/** Die `@`-Erwähnung direkt vor der Schreibmarke, sonst null. */
export function mentionAt(text: string, caret: number): { query: string; start: number } | null {
  const match = MENTION_RE.exec(text.slice(0, caret));
  if (!match) return null;
  return { query: match[2], start: caret - match[2].length - 1 };
}

/** Text nach der Auswahl: Die Erwähnung wird durch den Namen in Backticks ersetzt, die Schreibmarke steht dahinter. */
export function applyMention(text: string, caret: number, label: string): { text: string; caret: number } | null {
  const mention = mentionAt(text, caret);
  if (!mention) return null;
  const inserted = `\`${label}\` `;
  return { text: text.slice(0, mention.start) + inserted + text.slice(caret), caret: mention.start + inserted.length };
}

/**
 * Vorschläge für `@Name` im Chat: Codeobjekte (Programme, Klassen, Felder …) des gewählten Projekts aus der
 * globalen Suche. Der Name landet in Backticks in der Frage; das Belegpaket löst genannte Symbole auf.
 */
export function useEntityMentions(text: string, caret: number, projectId: number | null | undefined) {
  const mention = projectId ? mentionAt(text, caret) : null;
  const query = mention?.query ?? null;
  const [results, setResults] = useState<{ query: string; items: SearchResult[] } | null>(null);
  const [active, setActive] = useState(0);
  const [dismissed, setDismissed] = useState<string | null>(null);

  useEffect(() => {
    if (!query || !projectId) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api.searchGlobal(query, { types: 'entity', projectId, limit: 8, signal: controller.signal })
        .then(res => { setResults({ query, items: res.data.results }); setActive(0); })
        .catch(() => undefined);
    }, DEBOUNCE_MS);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, projectId]);

  const items = query && results?.query === query && dismissed !== query ? results.items : [];
  return {
    open: items.length > 0,
    items,
    active: Math.min(active, Math.max(0, items.length - 1)),
    move: (delta: number) => setActive(current => (items.length ? (current + delta + items.length) % items.length : 0)),
    dismiss: () => setDismissed(query),
  };
}
