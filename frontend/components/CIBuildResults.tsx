import { useLanguage } from '@/lib/i18n/LanguageContext';

type Value = Record<string, unknown>;
function object(value: unknown): Value {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Value : {};
}
function items(value: unknown): Value[] {
  return Array.isArray(value) ? value.map(object) : [];
}

export function CIBuildResults({ data }: { data: unknown }) {
  const { t } = useLanguage();
  const builds = object(data);
  return (
    <section className="rounded-lg border border-ds-zinc-500/30 p-3 text-xs">
      <h3 className="font-semibold">{t('ciBuild.results')}</h3>
      {builds.status !== 'found' && <p className="mt-2 text-ds-zinc-500">{t(`ciBuild.evidence.${String(builds.status || 'missing')}`)}</p>}
      {items(builds.items).map(run => {
        const summary = object(run.summary);
        const tests = object(summary.test_results);
        return (
          <article key={String(run.id)} className="mt-3 rounded border border-ds-zinc-500/30 p-3">
            {run.truncated === true && <p className="text-ds-amber-500">{t('ciBuild.truncated')}</p>}
            <p className="font-semibold">{String(run.provider)} · {String(run.job_name)} · {String(run.variant)}</p>
            <p className="mt-1">{String(run.run_id)} · {t('ciBuild.attempt')} {String(run.attempt)} · {t(`ciBuild.status.${String(run.status)}`)}</p>
            <p className="mt-1 break-all">{String(run.branch)} · {String(run.commit)}</p>
            <p className="mt-1 text-ds-zinc-500">{String(run.finished_at)}</p>
            {typeof run.pipeline_url === 'string' && <a className="mt-2 inline-block text-ds-indigo-400 underline" href={run.pipeline_url} target="_blank" rel="noopener noreferrer">{t('ciBuild.openPipeline')}</a>}
            <p className="mt-2">{t('ciBuild.tests')} · {t(`ciBuild.testsStatus.${String(summary.test_status || 'unknown')}`)}</p>
            <p>{t('ciBuild.counts', { tests: Number(tests.tests || 0), failures: Number(tests.failure || 0), errors: Number(tests.error || 0), skipped: Number(tests.skipped || 0) })}</p>
            <p className="mt-1 text-ds-zinc-500">{t('ciBuild.profiles')} {Array.isArray(summary.active_profiles) && summary.active_profiles.length ? summary.active_profiles.join(', ') : '—'}</p>
            {summary.java_version != null && <p className="text-ds-zinc-500">Java {String(summary.java_version)}</p>}
            {items(summary.modules).map(module => {
              const maven = object(module.maven);
              return (
                <details key={String(module.path)} className="mt-2">
                  <summary className="cursor-pointer text-ds-indigo-400">{String(module.path)}</summary>
                  {items(maven.modules).map((coordinate, index) => <p key={index} className="mt-1 break-all">{String(coordinate.groupId || '')}:{String(coordinate.artifactId)}:{String(coordinate.version || '')}</p>)}
                  <details className="mt-2">
                    <summary className="cursor-pointer">{t('ciBuild.dependencies')} · {items(maven.dependencies).length}</summary>
                    {items(maven.dependencies).map((dep, index) => <p key={index} className="break-all">{String(dep.groupId || '')}:{String(dep.artifactId)}:{String(dep.version || '')} · {String(dep.scope || '')}</p>)}
                    {maven.truncated === true && <p className="text-ds-amber-500">{t('ciBuild.truncated')}</p>}
                  </details>
                  {items(module.test_reports).map(report => <div key={String(report.path)} className="mt-2"><p className="break-all">{String(report.path)}</p>{items(report.failures).map((failure, index) => <p key={index} className="text-ds-red-500">{String(failure.class)} · {String(failure.name)} · {String(failure.status)}</p>)}</div>)}
                  {Array.isArray(module.collection_errors) && module.collection_errors.length > 0 && <p className="mt-2 text-ds-amber-500">{t('ciBuild.incomplete')} {module.collection_errors.join(', ')}</p>}
                </details>
              );
            })}
            {Array.isArray(summary.collection_errors) && summary.collection_errors.length > 0 && <p className="mt-2 text-ds-amber-500">{t('ciBuild.incomplete')} {summary.collection_errors.join(', ')}</p>}
          </article>
        );
      })}
      {builds.truncated === true && <p className="mt-2 text-ds-amber-500">{t('ciBuild.truncated')}</p>}
    </section>
  );
}
