import { useEffect, useRef, type Dispatch, type SetStateAction } from 'react';
import { getEntityTypeLabel } from '@/lib/graphTaxonomy';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import {
  EMPTY_LINK_RUN_SCOPE, isTargetedScope, selectedChunkCount, selectedEntityCount, setLanguageTypes, toggleValue,
  type LinkRunScope, type LinkScopeOptions,
} from '@/lib/linkRunScope';

interface Props {
  options: LinkScopeOptions | null;
  scope: LinkRunScope;
  setScope: Dispatch<SetStateAction<LinkRunScope>>;
}

const KNOWN_LANGUAGES = new Set(['cobol', 'java', 'jcl', 'maven', 'xml', 'sql', 'shell', 'other']);

function MixedCheckbox({ checked, mixed, label, onChange }: { checked: boolean; mixed: boolean; label: string; onChange: (value: boolean) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (ref.current) ref.current.indeterminate = mixed; }, [mixed]);
  return <input ref={ref} type="checkbox" aria-label={label} checked={checked}
    onClick={event => event.stopPropagation()} onChange={event => onChange(event.target.checked)} />;
}

/** Zwei Mengen eines Laufs: Code-Typen je Sprache und Wissensquellen mit Dokumentation. */
export function LinkRunScopePicker({ options, scope, setScope }: Props) {
  const { t, language: locale } = useLanguage();
  const number = (value: number) => value.toLocaleString(locale === 'en' ? 'en-US' : 'de-DE');
  const languageLabel = (key: string) => (KNOWN_LANGUAGES.has(key) ? t(`linkManagerView.runScope.languages.${key}`) : key);

  return <fieldset data-testid="link-run-scope" className="min-w-0 rounded-md border border-ds-zinc-500/25 p-3">
    <legend className="px-1 text-xs font-medium">{t('linkManagerView.runScope.title')}</legend>
    <p className="mb-3 text-xs leading-relaxed text-ds-zinc-500">{t('linkManagerView.runScope.hint')}</p>
    {!options ? <p className="text-xs text-ds-zinc-500">{t('linkManagerView.runScope.loading')}</p> : <>
      <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
        <section className="min-w-0">
          <h3 className="mb-2 text-xs font-medium">
            {t('linkManagerView.runScope.code', { count: number(selectedEntityCount(options, scope)) })}
          </h3>
          <div className="max-h-56 space-y-1 overflow-y-auto pr-1">
            {options.languages.length ? options.languages.map(language => {
              const chosen = language.types.filter(item => scope.entityTypes.includes(item.type)).length;
              const label = languageLabel(language.language);
              return <details key={language.language} open={chosen > 0 || options.languages.length === 1}
                className="rounded border border-ds-zinc-500/15 px-2 py-1">
                <summary className="flex cursor-pointer items-center gap-2 text-xs">
                  <MixedCheckbox label={t('linkManagerView.runScope.allOfLanguage', { language: label })}
                    checked={chosen === language.types.length} mixed={chosen > 0 && chosen < language.types.length}
                    onChange={checked => setScope(previous => ({ ...previous, entityTypes: setLanguageTypes(previous.entityTypes, language, checked) }))} />
                  <span className="min-w-0 flex-1 truncate font-medium">{label}</span>
                  <span className="shrink-0 tabular-nums text-ds-zinc-500">{number(language.count)}</span>
                </summary>
                <div className="mt-1 space-y-1 pb-1 pl-5">
                  {language.types.map(item => <label key={item.type} className="flex min-w-0 items-center gap-2 text-xs">
                    <input type="checkbox" checked={scope.entityTypes.includes(item.type)}
                      onChange={event => setScope(previous => ({ ...previous, entityTypes: toggleValue(previous.entityTypes, item.type, event.target.checked) }))} />
                    <span className="min-w-0 flex-1 truncate" title={item.type}>{getEntityTypeLabel(item.type, locale)}</span>
                    <span className="shrink-0 tabular-nums text-ds-zinc-500">{number(item.count)}</span>
                  </label>)}
                </div>
              </details>;
            }) : <p className="text-xs text-ds-zinc-500">{t('linkManagerView.runScope.noTypes')}</p>}
          </div>
        </section>
        <section className="min-w-0">
          <h3 className="mb-2 text-xs font-medium">
            {t('linkManagerView.runScope.docs', { count: number(selectedChunkCount(options, scope)) })}
          </h3>
          <div className="max-h-56 space-y-1 overflow-y-auto pr-1">
            {options.doc_sources.length ? options.doc_sources.map(source => <label key={source.id} className="flex min-w-0 items-center gap-2 text-xs">
              <input type="checkbox" checked={scope.docSourceIds.includes(source.id)}
                onChange={event => setScope(previous => ({ ...previous, docSourceIds: toggleValue(previous.docSourceIds, source.id, event.target.checked) }))} />
              <span className="min-w-0 flex-1 truncate" title={source.name}>{source.name || `#${source.id}`}</span>
              <span className="shrink-0 rounded bg-ds-zinc-500/15 px-1 text-[0.625rem]">{source.type}</span>
              <span className="shrink-0 tabular-nums text-ds-zinc-500">{number(source.chunk_count)}</span>
            </label>) : <p className="text-xs text-ds-zinc-500">{t('linkManagerView.runScope.noSources')}</p>}
          </div>
        </section>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className="min-w-0 flex-1 text-ds-zinc-500">
          {isTargetedScope(scope) ? t('linkManagerView.runScope.targeted') : t('linkManagerView.runScope.unrestricted')}
        </span>
        {isTargetedScope(scope) && <button type="button" onClick={() => setScope(EMPTY_LINK_RUN_SCOPE)} className="underline">
          {t('linkManagerView.runScope.reset')}
        </button>}
      </div>
    </>}
  </fieldset>;
}
