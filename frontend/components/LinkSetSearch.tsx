import { Check, Loader2, Plus, Search } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, API_URL } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import type { LinkSetItem } from '@/lib/linkSets';

interface Props {
  projectId: number;
  kind: string;
  placeholder: string;
  isAdded: (item: LinkSetItem) => boolean;
  onAdd: (items: LinkSetItem[]) => void;
  onRemove: (item: LinkSetItem) => void;
  describe: (item: LinkSetItem) => { label: string; detail: string; badge: string };
  inputClass: string;
}

/** Einzelne Objekte der Wissensbasis suchen und der Menge hinzufügen. */
export function LinkSetSearch({ projectId, kind, placeholder, isAdded, onAdd, onRemove, describe, inputClass }: Props) {
  const { t } = useLanguage();
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<{ query: string; items: LinkSetItem[]; failed: boolean } | null>(null);
  const trimmed = query.trim();

  useEffect(() => {
    if (!trimmed) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ kind, q: trimmed, limit: '25' });
      api.fetch(`${API_URL}/projects/${projectId}/link-runs/search?${params}`, { signal: controller.signal })
        .then(response => (response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`))))
        .then(data => setResult({ query: trimmed, items: Array.isArray(data?.items) ? data.items : [], failed: false }))
        .catch(() => { if (!controller.signal.aborted) setResult({ query: trimmed, items: [], failed: true }); });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [projectId, kind, trimmed]);

  const current = result && result.query === trimmed ? result : null;
  const loading = Boolean(trimmed) && !current;
  const missing = current?.items.filter(item => !isAdded(item)) ?? [];

  return <div className="space-y-3">
    <label className="relative block">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder={placeholder}
        aria-label={placeholder} className={`${inputClass} pl-8`} />
    </label>
    {!trimmed && <p className="text-xs text-muted-foreground">{t('linkManagerView.workspace.searchIdle')}</p>}
    {loading && <p className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" />{t('linkManagerView.workspace.searching')}</p>}
    {current?.failed && <p className="text-xs text-ds-amber-500">{t('linkManagerView.workspace.searchFailed')}</p>}
    {current && !current.failed && current.items.length === 0 && <p className="text-xs text-muted-foreground">{t('linkManagerView.workspace.noResults')}</p>}
    {current && current.items.length > 0 && <div className="rounded-md border border-border">
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-1.5 text-xs text-muted-foreground">
        <span>{t('linkManagerView.workspace.results', { count: current.items.length })}</span>
        {missing.length > 0 && <button type="button" onClick={() => onAdd(missing)} className="underline">{t('linkManagerView.workspace.addAll')}</button>}
      </div>
      <ul className="divide-y divide-border" data-testid={`link-set-search-results-${kind}`}>
        {current.items.map(item => {
          const added = isAdded(item);
          const { label, detail, badge } = describe(item);
          return <li key={JSON.stringify(item)} className={`flex min-w-0 items-center gap-3 px-3 py-2 text-xs ${added ? 'bg-primary/10' : 'hover:bg-muted'}`}>
            <span className="min-w-0 flex-1">
              <span className="flex min-w-0 items-center gap-2">
                <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[0.625rem] text-muted-foreground">{badge}</span>
                <span className="truncate font-medium" title={label}>{label}</span>
              </span>
              {detail && <span className="mt-0.5 block truncate text-muted-foreground" title={detail}>{detail}</span>}
            </span>
            <button type="button" onClick={() => (added ? onRemove(item) : onAdd([item]))}
              aria-label={`${added ? t('linkManagerView.workspace.remove') : t('linkManagerView.workspace.add')}: ${label}`}
              className={`flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 ${added ? 'border-primary text-primary' : 'border-border hover:border-primary/60'}`}>
              {added ? <Check aria-hidden className="h-3.5 w-3.5" /> : <Plus aria-hidden className="h-3.5 w-3.5" />}
              <span aria-hidden>{added ? t('linkManagerView.workspace.added') : t('linkManagerView.workspace.add')}</span>
            </button>
          </li>;
        })}
      </ul>
    </div>}
  </div>;
}
