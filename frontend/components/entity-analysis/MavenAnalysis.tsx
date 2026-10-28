import { useLanguage } from '@/lib/i18n/LanguageContext';
import { strings } from './metadata';

export function MavenAnalysis({ meta }: { meta: Record<string, unknown> }) {
  const { t } = useLanguage();
  if (!['maven_visibility', 'maven_active_profiles', 'maven_issues'].some(key => key in meta)) return null;
  return <section className="space-y-2 border-t border-ds-zinc-500/20 pt-2"><h4 className="font-semibold">{t('entityAnalysis.maven')}</h4>
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">{['module', 'source_set', 'maven_active_profiles', 'maven_visibility', 'maven_runtime_visibility'].map(key => <div key={key} className="contents"><dt className="text-ds-zinc-500">{t(`entityAnalysis.${key}`)}</dt><dd className="min-w-0 break-words font-mono">{strings(meta[key]).join(', ') || '—'}</dd></div>)}</dl>
    {strings(meta.maven_issues).length > 0 && <div role="status" className="rounded border border-ds-amber-500/40 bg-ds-amber-500/10 p-2"><p className="font-semibold text-ds-amber-500">{t('entityAnalysis.mavenIssues')}</p><ul className="list-inside list-disc">{strings(meta.maven_issues).map((issue, index) => <li key={index} className="break-words">{issue}</li>)}</ul></div>}
  </section>;
}
