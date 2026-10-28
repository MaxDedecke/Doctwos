import { useLanguage } from '@/lib/i18n/LanguageContext';
import { records, record, strings, text, type OpenLine } from './metadata';

export function MethodAnalysis({ meta, onLine }: { meta: Record<string, unknown>; onLine: OpenLine }) {
  const { t } = useLanguage();
  const returns = records(meta.return_expressions);
  const exceptions = records(meta.exception_flow);
  const flow = records(meta.data_flow);
  const annotations = records(meta.annotation_details);
  return <>
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
      {['return_type', 'parameter_types', 'type_parameters', 'throws_types', 'visibility', 'modifiers', 'field_type', 'variable_type', 'parameter_type', 'component_type'].map(key => {
        const value = strings(meta[key]).join(', ');
        return value ? <div key={key} className="contents"><dt className="text-ds-zinc-500">{t(`entityAnalysis.${key}`)}</dt><dd className="min-w-0 break-words font-mono">{value}</dd></div> : null;
      })}
    </dl>
    {(annotations.length > 0 || strings(meta.annotations).length > 0) && <section><h4 className="font-semibold">{t('entityAnalysis.annotations')}</h4><ul className="space-y-1">{annotations.length ? annotations.map((item, index) => <li key={index} className="break-words font-mono">{text(item.source) || `@${text(item.name)} ${JSON.stringify(item.values || {})}`}</li>) : strings(meta.annotations).map(name => <li key={name} className="font-mono">@{name}</li>)}</ul></section>}
    {returns.length > 0 && <section><h4 className="font-semibold">{t('entityAnalysis.returns')}</h4>{returns.map((item, index) => <div key={index} className="flex items-start gap-2"><Line value={item.start_line} onLine={onLine} /><code className="break-words">{text(item.expression)}</code></div>)}</section>}
    {exceptions.length > 0 && <section><h4 className="font-semibold">{t('entityAnalysis.exceptions')}</h4>{exceptions.map((item, index) => <div key={index} className="flex items-start gap-2"><Line value={item.start_line} onLine={onLine} /><span>{text(item.kind)} {strings(item.exception_types).join(' | ') || text(item.exception_type)} {text(item.expression)} {text(item.control_context)}</span></div>)}</section>}
    {meta.synthetic === true && <p className="text-ds-zinc-500">{t('entityAnalysis.synthetic', { origin: text(meta.generated_by) })}</p>}
    {meta.data_flow_truncated === true && <p role="status" className="rounded border border-ds-amber-500/40 bg-ds-amber-500/10 p-2 text-ds-amber-500">{t('entityAnalysis.flowLimited', { count: typeof meta.data_flow_omitted === 'number' ? meta.data_flow_omitted : 0 })}</p>}
    {flow.length > 0 && <section><h4 className="mb-1 font-semibold">{t('entityAnalysis.dataFlow')}</h4><div className="overflow-x-auto"><table className="w-full text-left"><thead><tr>{['line', 'operation', 'target', 'origin', 'statement'].map(key => <th key={key} className="p-1 text-ds-zinc-500">{t(`entityAnalysis.${key}`)}</th>)}</tr></thead><tbody>{flow.map((item, index) => <tr key={index} className="border-t border-ds-zinc-500/20 align-top">
      <td className="p-1"><Line value={item.line} onLine={onLine} /></td><td className="p-1">{t(`entityAnalysis.operations.${text(item.operation)}`)}</td><td className="p-1 font-mono">{text(record(item.target).name)}</td><td className="p-1 font-mono">{records(item.sources).map(source => text(source.name)).join(', ')}</td><td className="p-1 whitespace-pre-wrap font-mono">{text(item.text)}</td>
    </tr>)}</tbody></table></div></section>}
  </>;
}

function Line({ value, onLine }: { value: unknown; onLine: OpenLine }) {
  return typeof value === 'number' ? <button type="button" className="shrink-0 text-ds-indigo-400 underline" onClick={() => onLine(value)}>L{value}</button> : null;
}
