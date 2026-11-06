import { Loader2, X } from 'lucide-react';
import { getEntityTypeLabel } from '@/lib/graphTaxonomy';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import {
  addItem, clearSelection, hasItem, removeItem, selectionCount, setFacetGroup, toggleFacetValue, withMode,
  type FacetValue, type KindOptions, type LinkSetDef, type LinkSetItem, type SetPreview,
} from '@/lib/linkSets';
import { LinkFacetPicker } from './LinkFacetPicker';
import { LinkSetSearch } from './LinkSetSearch';

interface Props {
  side: 'a' | 'b';
  projectId: number;
  set: LinkSetDef;
  kindOptions: KindOptions | undefined;
  preview: { data: SetPreview | null; loading: boolean; error: string | null };
  onChange: (change: (set: LinkSetDef) => LinkSetDef) => void;
  inputClass: string;
}

/** Übersetzung mit Rückfall: unbekannte Sprachen, Quelltypen und Facetten erscheinen mit ihrem Schlüssel. */
export function useLabel() {
  const { t } = useLanguage();
  return (key: string, fallback: string, values?: Record<string, string | number>) => {
    const text = t(key, values);
    return text === key ? fallback : text;
  };
}

/** Eine Menge der Analyse: alles einer Art oder eine eigene Auswahl aus Facetten und gesuchten Objekten. */
export function LinkSetPanel({ side, projectId, set, kindOptions, preview, onChange, inputClass }: Props) {
  const { t, language } = useLanguage();
  const label = useLabel();
  const number = (value: number) => value.toLocaleString(language === 'en' ? 'en-US' : 'de-DE');
  const kindLabel = label(`linkManagerView.workspace.kinds.${set.kind}`, set.kind);
  const groupLabel = (facet: string) => (key: string) => facet === 'entity_type'
    ? label(`linkManagerView.workspace.languages.${key}`, key)
    : label(`linkManagerView.workspace.sourceTypes.${key}`, key);
  const valueLabel = (facet: string) => (value: FacetValue) => (facet === 'entity_type' ? getEntityTypeLabel(value.value, language) : value.label ?? value.value);
  // Auch ein Filter mit nur einem Wert bleibt sichtbar (z. B. die einzige Wissensquelle): Man soll sehen, was es gibt.
  const facets = (kindOptions?.facets ?? []).filter(facet => facet.groups.some(group => group.values.length > 0));

  const describe = (item: LinkSetItem) => {
    const badge = item.entity_type ? getEntityTypeLabel(item.entity_type, language)
      : item.group ? label(`linkManagerView.workspace.sourceTypes.${item.group}`, item.group) : item.kind;
    const extra = typeof item.chunk_count === 'number' ? t('linkManagerView.workspace.chunks', { count: item.chunk_count }) : '';
    return { label: String(item.label ?? item.kind), detail: [item.detail, extra].filter(Boolean).join(' · '), badge };
  };
  const storedDetail = (item: LinkSetItem): LinkSetItem => {
    const { badge, detail } = describe(item);
    return { ...item, detail: [badge, detail].filter(Boolean).join(' · ') };
  };

  const custom = set.mode === 'custom';
  const count = preview.data ? (set.kind === 'docs' && typeof preview.data.documents === 'number'
    ? t('linkManagerView.workspace.docCount', { count: number(preview.data.count), documents: number(preview.data.documents) })
    : t('linkManagerView.workspace.objectCount', { count: number(preview.data.count) })) : null;

  return <section data-testid={`link-set-${side}`} aria-label={`${label(`linkManagerView.workspace.set.${side}`, side)} · ${kindLabel}`}
    className="flex min-h-0 min-w-0 flex-col rounded-lg border border-ds-zinc-500/25">
    <header className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-ds-zinc-500/20 px-4 py-3">
      <h3 className="text-sm font-semibold">{label(`linkManagerView.workspace.set.${side}`, side)} · {kindLabel}</h3>
      <span className="min-w-0 flex-1 truncate text-right text-xs tabular-nums text-ds-zinc-500" aria-live="polite" title={count ?? undefined}>
        {preview.loading ? <Loader2 className="ml-auto h-3.5 w-3.5 animate-spin" /> : count}
      </span>
    </header>
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
      <div role="radiogroup" aria-label={t('linkManagerView.workspace.modeLabel')} className="grid grid-cols-2 gap-2">
        {(['all', 'custom'] as const).map(mode => <label key={mode}
          className={`flex cursor-pointer flex-col rounded-md border px-3 py-2 text-xs ${set.mode === mode ? 'border-ds-indigo-500 bg-ds-indigo-500/10' : 'border-ds-zinc-500/25'}`}>
          <span className="flex items-center gap-2 font-medium">
            <input type="radio" name={`link-set-mode-${side}`} checked={set.mode === mode} onChange={() => onChange(current => withMode(current, mode))} />
            {mode === 'all'
              ? t('linkManagerView.workspace.modes.all', { kind: kindLabel, count: number(kindOptions?.total ?? 0) })
              : t('linkManagerView.workspace.modes.custom')}
          </span>
          <span className="mt-1 text-[0.625rem] leading-snug text-ds-zinc-500">{t(`linkManagerView.workspace.modeHints.${mode}`)}</span>
        </label>)}
      </div>

      {custom && <>
        {facets.length > 0 && <div className="space-y-2">
          <h4 className="text-xs font-medium">{t('linkManagerView.workspace.filterTitle')}</h4>
          {facets.map(facet => <LinkFacetPicker key={facet.name} facet={facet}
            title={label(`linkManagerView.workspace.facets.${set.kind}.${facet.name}`, facet.name)}
            selected={set.facets[facet.name] ?? []} groupLabel={groupLabel(facet.name)} valueLabel={valueLabel(facet.name)}
            formatCount={number} allOfLabel={group => t('linkManagerView.workspace.allOf', { group })}
            onToggle={(value, checked) => onChange(current => toggleFacetValue(current, facet.name, value, checked))}
            onGroup={(group, checked) => onChange(current => setFacetGroup(current, facet.name, group, checked))} />)}
          <p className="text-[0.625rem] leading-snug text-ds-zinc-500">{t('linkManagerView.workspace.filterHint')}</p>
        </div>}

        <div className="space-y-2">
          <h4 className="text-xs font-medium">{t('linkManagerView.workspace.searchTitle')}</h4>
          <LinkSetSearch projectId={projectId} kind={set.kind} inputClass={inputClass}
            placeholder={label(`linkManagerView.workspace.searchPlaceholder.${set.kind}`, t('linkManagerView.workspace.searchTitle'))}
            isAdded={item => hasItem(set, item)} describe={describe}
            onAdd={items => onChange(current => items.reduce((next, item) => addItem(next, storedDetail(item)), current))}
            onRemove={item => onChange(current => removeItem(current, item))} />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h4 className="min-w-0 flex-1 text-xs font-medium">{t('linkManagerView.workspace.picked', { count: set.items.length })}</h4>
            {selectionCount(set) > 0 && <button type="button" onClick={() => onChange(clearSelection)} className="text-xs underline">
              {t('linkManagerView.workspace.clear')}
            </button>}
          </div>
          {set.items.length === 0
            ? <p className="rounded-md border border-dashed border-ds-zinc-500/30 p-3 text-xs text-ds-zinc-500">{t('linkManagerView.workspace.pickedEmpty')}</p>
            : <ul className="max-h-60 space-y-1 overflow-y-auto" data-testid={`link-set-items-${side}`}>
              {set.items.map(item => <li key={JSON.stringify(item)} className="flex min-w-0 items-center gap-2 rounded bg-ds-zinc-500/10 px-2 py-1 text-xs">
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium" title={String(item.label ?? '')}>{String(item.label ?? item.kind)}</span>
                  {item.detail && <span className="block truncate text-[0.625rem] text-ds-zinc-500">{String(item.detail)}</span>}
                </span>
                <button type="button" onClick={() => onChange(current => removeItem(current, item))}
                  aria-label={`${t('linkManagerView.workspace.remove')}: ${String(item.label ?? item.kind)}`} className="shrink-0 rounded p-1 hover:bg-ds-zinc-500/20">
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>)}
            </ul>}
        </div>
      </>}

      <details className="rounded-md border border-ds-zinc-500/20" data-testid={`link-set-preview-${side}`}>
        <summary className="cursor-pointer px-3 py-2 text-xs font-medium">{t('linkManagerView.workspace.previewTitle')}</summary>
        <div className="px-3 pb-2 text-xs">
          {preview.error && <p className="text-ds-amber-500">{preview.error}</p>}
          {preview.data && preview.data.sample.length === 0 && <p className="text-ds-zinc-500">{t('linkManagerView.workspace.previewEmpty')}</p>}
          {preview.data && preview.data.sample.length > 0 && <ul className="space-y-1">
            {preview.data.sample.map(item => {
              const shown = describe(item);
              return <li key={JSON.stringify(item)} className="min-w-0">
                <span className="mr-2 rounded bg-ds-zinc-500/15 px-1 text-[0.625rem]">{shown.badge}</span>
                <span className="font-medium">{shown.label}</span>
                {shown.detail && <span className="block truncate text-[0.625rem] text-ds-zinc-500">{shown.detail}</span>}
              </li>;
            })}
          </ul>}
        </div>
      </details>
    </div>
  </section>;
}
