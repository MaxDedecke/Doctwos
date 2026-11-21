import { api } from '@/app/services/api';
import { HighlightedCode } from '@/components/HighlightedCode';
import { languageForPath } from '@/lib/codeHighlight';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useEffect, useState } from 'react';

const BEFORE = 2;
const AFTER = 5;
// Je Datei einmal laden; mehrere Zitate derselben Datei teilen sich die Anfrage.
const fileCache = new Map<string, Promise<string[]>>();

function fileLines(sourceId: number | string, path: string): Promise<string[]> {
  const key = `${sourceId}:${path}`;
  let lines = fileCache.get(key);
  if (!lines) {
    lines = api.getKnowledgeSourceContent(sourceId, path).then(res => (res.data.format === 'text' ? res.data.content.split('\n') : []));
    lines.catch(() => fileCache.delete(key));
    fileCache.set(key, lines);
  }
  return lines;
}

/** Die zitierten Zeilen mit etwas Umgebung, für die Hover-Karte eines Zitats. */
export function CitedLinesPreview({ sourceId, path, line }: { sourceId: number | string; path: string; line: number }) {
  const { t } = useLanguage();
  const [lines, setLines] = useState<string[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    fileLines(sourceId, path).then(all => { if (active) setLines(all); }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [sourceId, path]);

  if (failed) return null;
  if (!lines) return <p className="px-2 py-1 text-[0.6875rem] opacity-60">{t('pathCard.loadingPreview')}</p>;
  const first = Math.max(1, line - BEFORE);
  const excerpt = lines.slice(first - 1, line + AFTER);
  if (!excerpt.length) return null;
  return (
    <pre aria-label={t('pathCard.preview')} className="mx-2 my-1 max-h-48 overflow-auto rounded border border-ds-zinc-500/20 p-2 font-mono text-[0.6875rem] leading-relaxed">
      <code><HighlightedCode code={excerpt.join('\n')} language={languageForPath(path)} firstLine={first} markLine={line} /></code>
    </pre>
  );
}
