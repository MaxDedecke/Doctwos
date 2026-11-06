import { getEntityTypeLabel } from '@/lib/graphTaxonomy';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import type { KindOptions, LinkSetDef, LinkSetItem } from '@/lib/linkSets';

/** Beschriftungen der Analyse-Arbeitsfläche. Unbekannte Sprachen, Quelltypen, Facetten und Mengenarten erscheinen
 *  mit ihrem Schlüssel; für einen schönen Namen reicht ein Übersetzungseintrag. */
export function useLinkSetLabels() {
  const { t, language } = useLanguage();
  const label = (key: string, fallback: string, values?: Record<string, string | number>) => {
    const text = t(key, values);
    return text === key ? fallback : text;
  };
  const number = (value: number) => value.toLocaleString(language === 'en' ? 'en-US' : 'de-DE');
  const kindLabel = (kind: string) => label(`linkManagerView.workspace.kinds.${kind}`, kind);
  const setLabel = (side: string) => label(`linkManagerView.workspace.set.${side}`, side);
  const facetTitle = (kind: string, facet: string) => label(`linkManagerView.workspace.facets.${kind}.${facet}`, facet);
  const groupLabel = (facet: string, key: string) => (facet === 'entity_type'
    ? label(`linkManagerView.workspace.languages.${key}`, key)
    : label(`linkManagerView.workspace.sourceTypes.${key}`, key));

  /** Anzeigename eines Facettenwerts; Quellen tragen ihren Namen in den Optionen. */
  const valueLabel = (facet: string, value: string, options?: KindOptions) => {
    if (facet === 'entity_type') return getEntityTypeLabel(value, language);
    const known = options?.facets.find(item => item.name === facet)?.groups
      .flatMap(group => group.values).find(item => item.value === value);
    return known?.label ?? value;
  };

  const describe = (item: LinkSetItem) => {
    const badge = item.entity_type ? getEntityTypeLabel(item.entity_type, language)
      : item.group ? groupLabel('source', item.group) : item.kind;
    const extra = typeof item.chunk_count === 'number' ? t('linkManagerView.workspace.chunks', { count: item.chunk_count }) : '';
    return { label: String(item.label ?? item.kind), detail: [item.detail, extra].filter(Boolean).join(' · '), badge };
  };

  /** Eine Zeile für die Übersichtskarte: was die Menge ausmacht. */
  const summary = (set: LinkSetDef, options?: KindOptions) => {
    if (set.mode === 'all') return t('linkManagerView.workspace.summaryAll');
    const parts = Object.entries(set.facets).filter(([, values]) => values.length > 0).map(([facet, values]) => {
      const names = values.slice(0, 2).map(value => valueLabel(facet, value, options));
      const rest = values.length - names.length;
      return `${facetTitle(set.kind, facet)}: ${names.join(', ')}${rest > 0 ? ` +${rest}` : ''}`;
    });
    if (set.items.length) parts.push(t('linkManagerView.workspace.summaryItems', { count: set.items.length }));
    return parts.length ? parts.join(' · ') : t('linkManagerView.workspace.summaryEmpty');
  };

  return { t, language, label, number, kindLabel, setLabel, facetTitle, groupLabel, valueLabel, describe, summary };
}
