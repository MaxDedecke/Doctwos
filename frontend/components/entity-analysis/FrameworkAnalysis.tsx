import type { CodeEntity, EntityNeighbor } from '@/types/domain';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { record, records, strings, text } from './metadata';

export function FrameworkAnalysis({ meta, neighbors, truncated, onOpen }: { meta: Record<string, unknown>; neighbors: EntityNeighbor[]; truncated: boolean; onOpen: (entity: CodeEntity) => void }) {
  const { t } = useLanguage();
  const bean = record(meta.bean);
  const hasBean = Object.keys(bean).length > 0;
  const endpoint = meta.protocol === 'http' || meta.protocol === 'soap';
  return <>
    {endpoint && <section className="space-y-1"><h4 className="font-semibold">{t('entityAnalysis.endpoint')}</h4><dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">{['protocol', 'framework', 'http_method', 'path', 'path_expression', 'namespace', 'operation', 'service_name', 'port_type', 'consumes', 'produces'].map(key => {
      const value = strings(meta[key]).join(', ');
      return value ? <div key={key} className="contents"><dt className="text-ds-zinc-500">{t(`entityAnalysis.${key}`)}</dt><dd className="min-w-0 break-words font-mono">{value}</dd></div> : null;
    })}</dl>{records(meta.parameters).map((parameter, index) => <p key={index} className="break-words font-mono">{text(parameter.name)}: {text(parameter.type)} {records(parameter.annotations).map(annotation => `@${text(annotation.name)} ${JSON.stringify(annotation.values || {})}`).join(' ')}</p>)}</section>}
    {hasBean && <section className="space-y-1"><h4 className="font-semibold">{t('entityAnalysis.bean')}</h4><p>{t(bean.activation_unknown ? 'entityAnalysis.activationUnknown' : bean.active ? 'entityAnalysis.active' : 'entityAnalysis.inactive')}{bean.primary === true && ` · ${t('entityAnalysis.primary')}`}</p><dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">{['framework', 'names', 'provided_type', 'profiles', 'scopes'].map(key => <div key={key} className="contents"><dt className="text-ds-zinc-500">{t(`entityAnalysis.${key}`)}</dt><dd className="min-w-0 break-words font-mono">{strings(bean[key]).join(', ') || '—'}</dd></div>)}</dl></section>}
    {neighbors.length > 0 && <section><h4 className="font-semibold">{t('entityAnalysis.bindings')}</h4><ul className="space-y-1">{neighbors.map(neighbor => <li key={`${neighbor.type}:${neighbor.edge_id}`} className="flex flex-wrap items-baseline gap-2"><span className="text-ds-zinc-500">{t(`entityAnalysis.${neighbor.direction === 'in' ? 'relationsIncoming' : 'relations'}.${neighbor.type}`)}</span>{neighbor.entity ? <button type="button" className="break-words text-left text-ds-indigo-400 underline" onClick={() => onOpen(neighbor.entity!)}>{neighbor.entity.qualified_name || neighbor.entity.name}</button> : <span>{neighbor.dst_name}</span>}<span>{t(`callGraphView.resolution.${neighbor.resolution || 'unresolved'}`)}</span></li>)}</ul>{truncated && <p className="mt-1 text-ds-zinc-500">{t('entityAnalysis.bindingsLimited')}</p>}</section>}
  </>;
}
