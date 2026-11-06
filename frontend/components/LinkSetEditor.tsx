import { Loader2, X } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useLinkSetLabels } from '@/hooks/useLinkSetLabels';
import {
  addItem, clearSelection, hasItem, removeItem, selectionCount, setFacetGroup, toggleFacetValue, withMode,
  type KindOptions, type LinkSetDef, type LinkSetItem, type SetMode, type SetPreview,
} from '@/lib/linkSets';
import { cn } from '@/lib/utils';
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

const VISIBLE_ITEMS = 30;

/** Spalte der Arbeitsfläche: Kopf fest, Inhalt scrollt ab breiten Bildschirmen für sich (nie in einer zweiten Scrollfläche). */
function Column({ step, title, hint, children, testId, highlight }: { step?: string; title: string; hint?: string; children: ReactNode; testId?: string; highlight?: boolean }) {
  return <section data-testid={testId} aria-label={title}
    className={cn('flex min-w-0 flex-col rounded-lg border bg-card lg:min-h-0', highlight ? 'border-primary/50' : 'border-border')}>
    <header className="shrink-0 border-b border-border px-4 py-3">
      <h4 className="flex items-center gap-2 text-sm font-semibold">
        {step && <span aria-hidden className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-[0.625rem] text-muted-foreground">{step}</span>}
        {title}
      </h4>
      {hint && <p className="mt-1 text-xs leading-snug text-muted-foreground">{hint}</p>}
    </header>
    <div className="space-y-4 p-4 lg:min-h-0 lg:flex-1 lg:overflow-y-auto">{children}</div>
  </section>;
}

function Sample({ preview, describe, emptyText }: { preview: Props['preview']; describe: ReturnType<typeof useLinkSetLabels>['describe']; emptyText: string }) {
  if (preview.error) return <p className="text-xs text-destructive">{preview.error}</p>;
  if (!preview.data) return null;
  if (preview.data.sample.length === 0) return <p className="text-xs text-muted-foreground">{emptyText}</p>;
  return <ul className="divide-y divide-border rounded-md border border-border text-xs">
    {preview.data.sample.map(item => {
      const shown = describe(item);
      return <li key={JSON.stringify(item)} className="min-w-0 px-3 py-1.5">
        <span className="mr-2 rounded bg-muted px-1.5 py-0.5 text-[0.625rem] text-muted-foreground">{shown.badge}</span>
        <span className="font-medium">{shown.label}</span>
        {shown.detail && <span className="block truncate text-muted-foreground">{shown.detail}</span>}
      </li>;
    })}
  </ul>;
}

/** Eine Menge bearbeiten: alles einer Art oder eine eigene Auswahl aus Merkmalen und einzeln gesuchten Objekten. */
export function LinkSetEditor({ side, projectId, set, kindOptions, preview, onChange, inputClass }: Props) {
  const labels = useLinkSetLabels();
  const { t, number, describe } = labels;
  const [showSample, setShowSample] = useState(false);
  const [showAllItems, setShowAllItems] = useState(false);
  const setName = labels.setLabel(side);
  const kindName = labels.kindLabel(set.kind);
  const facets = (kindOptions?.facets ?? []).filter(facet => facet.groups.some(group => group.values.length > 0));
  const count = preview.data
    ? (set.kind === 'docs' && typeof preview.data.documents === 'number'
      ? t('linkManagerView.workspace.docCount', { count: number(preview.data.count), documents: number(preview.data.documents) })
      : t('linkManagerView.workspace.objectCount', { count: number(preview.data.count) }))
    : null;
  const storedDetail = (item: LinkSetItem): LinkSetItem => {
    const { badge, detail } = describe(item);
    return { ...item, detail: [badge, detail].filter(Boolean).join(' · ') };
  };
  const chosenFacets = Object.entries(set.facets).filter(([, values]) => values.length > 0);
  const items = showAllItems ? set.items : set.items.slice(0, VISIBLE_ITEMS);

  const modeSwitch = <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2">
    <div role="radiogroup" aria-label={t('linkManagerView.workspace.modeLabel')} className="inline-flex rounded-lg border border-border bg-muted p-1">
      {(['all', 'custom'] as SetMode[]).map(mode => <label key={mode}
        className={cn('flex cursor-pointer items-center rounded-md px-3 py-1.5 text-xs font-medium has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring',
          set.mode === mode ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground')}>
        <input type="radio" className="sr-only" name={`link-set-mode-${side}`} checked={set.mode === mode}
          onChange={() => onChange(current => withMode(current, mode))} />
        {mode === 'all'
          ? t('linkManagerView.workspace.modes.all', { count: number(kindOptions?.total ?? 0) })
          : t('linkManagerView.workspace.modes.custom')}
      </label>)}
    </div>
    <p className="min-w-0 flex-1 text-xs text-muted-foreground">{t(`linkManagerView.workspace.modeHints.${set.mode}`)}</p>
  </div>;

  if (set.mode === 'all') {
    return <div data-testid={`link-set-${side}`} className="flex min-h-0 flex-1 flex-col gap-4">
      {modeSwitch}
      <div className="min-h-0 flex-1 lg:overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-4 rounded-lg border border-border bg-card p-6">
          <p className="text-sm">{t('linkManagerView.workspace.allContents', { count: number(kindOptions?.total ?? 0), kind: kindName })}</p>
          <button type="button" onClick={() => onChange(current => withMode(current, 'custom'))}
            className="rounded-md border border-border px-3 py-1.5 text-xs hover:border-primary/60">{t('linkManagerView.workspace.switchToCustom')}</button>
          <h5 className="pt-2 text-xs font-semibold">{t('linkManagerView.workspace.sampleTitle')}</h5>
          <Sample preview={preview} describe={describe} emptyText={t('linkManagerView.workspace.previewEmpty')} />
        </div>
      </div>
    </div>;
  }

  return <div data-testid={`link-set-${side}`} className="flex min-h-0 flex-1 flex-col gap-4">
    {modeSwitch}
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)_minmax(0,0.95fr)]">
      <Column step="1" title={t('linkManagerView.workspace.filterTitle')} hint={t('linkManagerView.workspace.filterHint')}>
        {facets.length === 0 ? <p className="text-xs text-muted-foreground">{t('linkManagerView.workspace.noFilters')}</p>
          : facets.map(facet => <LinkFacetPicker key={facet.name} facet={facet}
            title={labels.facetTitle(set.kind, facet.name)} selected={set.facets[facet.name] ?? []}
            groupLabel={key => labels.groupLabel(facet.name, key)}
            valueLabel={value => labels.valueLabel(facet.name, value.value, kindOptions)}
            formatCount={number} allOfLabel={group => t('linkManagerView.workspace.allOf', { group })}
            moreLabel={hidden => t('linkManagerView.workspace.moreValues', { count: hidden })}
            lessLabel={t('linkManagerView.workspace.fewerValues')}
            chosenLabel={chosen => t('linkManagerView.workspace.chosen', { count: chosen })}
            onToggle={(value, checked) => onChange(current => toggleFacetValue(current, facet.name, value, checked))}
            onGroup={(group, checked) => onChange(current => setFacetGroup(current, facet.name, group, checked))} />)}
      </Column>

      <Column step="2" title={t('linkManagerView.workspace.searchTitle')} hint={t('linkManagerView.workspace.searchHint')}>
        <LinkSetSearch projectId={projectId} kind={set.kind} inputClass={inputClass}
          placeholder={labels.label(`linkManagerView.workspace.searchPlaceholder.${set.kind}`, t('linkManagerView.workspace.searchTitle'))}
          isAdded={item => hasItem(set, item)} describe={describe}
          onAdd={found => onChange(current => found.reduce((next, item) => addItem(next, storedDetail(item)), current))}
          onRemove={item => onChange(current => removeItem(current, item))} />
      </Column>

      <Column title={t('linkManagerView.workspace.contentsTitle', { set: setName })} testId={`link-set-contents-${side}`} highlight>
        <p className="flex items-center gap-2 text-lg font-semibold tabular-nums" aria-live="polite">
          {preview.loading ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : count}
        </p>
        {selectionCount(set) === 0 && <p className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
          {t('linkManagerView.workspace.contentsEmpty')}
        </p>}
        {chosenFacets.length > 0 && <div className="space-y-2">
          <h5 className="text-xs font-semibold">{t('linkManagerView.workspace.fromFilters')}</h5>
          {chosenFacets.map(([facet, values]) => <div key={facet} className="space-y-1">
            <p className="text-xs text-muted-foreground">{labels.facetTitle(set.kind, facet)}</p>
            <div className="flex flex-wrap gap-1.5">
              {values.map(value => {
                const text = labels.valueLabel(facet, value, kindOptions);
                return <span key={value} className="inline-flex max-w-full items-center gap-1 rounded-full border border-primary/50 bg-primary/10 py-0.5 pl-2.5 pr-1 text-xs">
                  <span className="min-w-0 truncate" title={text}>{text}</span>
                  <button type="button" onClick={() => onChange(current => toggleFacetValue(current, facet, value, false))}
                    aria-label={`${t('linkManagerView.workspace.removeFilter')}: ${text}`} className="rounded-full p-0.5 hover:bg-muted">
                    <X aria-hidden className="h-3 w-3" />
                  </button>
                </span>;
              })}
            </div>
          </div>)}
        </div>}
        {set.items.length > 0 && <div className="space-y-2">
          <h5 className="text-xs font-semibold">{t('linkManagerView.workspace.picked', { count: set.items.length })}</h5>
          <ul className="divide-y divide-border rounded-md border border-border" data-testid={`link-set-items-${side}`}>
            {items.map(item => <li key={JSON.stringify(item)} className="flex min-w-0 items-center gap-2 px-3 py-1.5 text-xs">
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium" title={String(item.label ?? '')}>{String(item.label ?? item.kind)}</span>
                {item.detail && <span className="block truncate text-muted-foreground">{String(item.detail)}</span>}
              </span>
              <button type="button" onClick={() => onChange(current => removeItem(current, item))}
                aria-label={`${t('linkManagerView.workspace.remove')}: ${String(item.label ?? item.kind)}`} className="shrink-0 rounded p-1 hover:bg-muted">
                <X aria-hidden className="h-3.5 w-3.5" />
              </button>
            </li>)}
          </ul>
          {set.items.length > VISIBLE_ITEMS && <button type="button" onClick={() => setShowAllItems(value => !value)} className="text-xs text-primary hover:underline">
            {showAllItems ? t('linkManagerView.workspace.fewerValues') : t('linkManagerView.workspace.showAllItems', { count: set.items.length })}
          </button>}
        </div>}
        {selectionCount(set) > 0 && <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
          <button type="button" onClick={() => setShowSample(value => !value)} className="text-xs text-primary hover:underline">
            {showSample ? t('linkManagerView.workspace.hideSample') : t('linkManagerView.workspace.showSample')}
          </button>
          <button type="button" onClick={() => onChange(clearSelection)} className="text-xs text-muted-foreground hover:text-foreground hover:underline">
            {t('linkManagerView.workspace.clear')}
          </button>
        </div>}
        {showSample && <Sample preview={preview} describe={describe} emptyText={t('linkManagerView.workspace.previewEmpty')} />}
      </Column>
    </div>
  </div>;
}
