"use client";

import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import React from 'react';
import { api } from '@/app/services/api';
import {
  formFromProfile, LANGUAGE_LABELS, LITERAL_DELIMITERS, profileFromForm, SOURCE_FORMATS,
  type BuildProfileView, type PreflightReport, type ProfileForm,
} from '@/lib/buildProfileForm';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';

interface Props {
  source: { id: number; name: string } | null;
  canEdit: boolean;
  onClose: () => void;
}

const COMPILER_FAMILIES = ['IBM_ENTERPRISE_COBOL', 'MICRO_FOCUS', 'GNUCOBOL', 'FUJITSU_COBOL2000'];
const STATUSES = ['complete', 'partial', 'text_fallback', 'skipped', 'error'] as const;
const input = 'w-full rounded-md border border-border bg-background px-2 py-1.5 text-xs outline-none focus:border-primary disabled:opacity-60';

function errorText(error: unknown): string | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' ? detail : null;
}

/** Buildprofil und Preflight-Bericht einer Git-Quelle: was wie gelesen wurde, wo die Analyse hakt, und die Einstellungen dazu. */
export function SourceProfileDialog({ source, canEdit, onClose }: Props) {
  const { t } = useLanguage();
  return <Dialog.Root open={source !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-[110] bg-ds-black/50 backdrop-blur-sm" />
      <Dialog.Content data-testid="source-profile-dialog"
        className="fixed left-1/2 top-1/2 z-[111] flex max-h-[88vh] w-[calc(100%_-_2rem)] max-w-4xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-border bg-background text-foreground shadow-2xl">
        <div className="flex items-start gap-3 border-b border-border p-5 pb-3">
          <div className="min-w-0 flex-1">
            <Dialog.Title className="truncate text-base font-semibold">{t('settings.sourceProfile.title', { name: source?.name ?? '' })}</Dialog.Title>
            <Dialog.Description className="mt-0.5 text-xs text-muted-foreground">{t('settings.sourceProfile.description')}</Dialog.Description>
          </div>
          <Dialog.Close aria-label={t('settings.sourceProfile.close')} className="shrink-0 rounded-md p-1.5 hover:bg-muted"><X className="h-4 w-4" /></Dialog.Close>
        </div>
        {source && <ProfileBody key={source.id} sourceId={source.id} canEdit={canEdit} />}
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}

function ProfileBody({ sourceId, canEdit }: { sourceId: number; canEdit: boolean }) {
  const { t } = useLanguage();
  const [tab, setTab] = React.useState<'preflight' | 'profile'>('preflight');
  const [preflight, setPreflight] = React.useState<PreflightReport | null>(null);
  const [view, setView] = React.useState<BuildProfileView | null>(null);
  const [form, setForm] = React.useState<ProfileForm | null>(null);
  const [loadError, setLoadError] = React.useState(false);
  const [saveState, setSaveState] = React.useState<{ kind: 'saving' | 'saved' | 'error'; message?: string } | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    Promise.all([api.getPreflight(sourceId), api.getBuildProfile(sourceId)])
      .then(([report, profile]) => {
        if (cancelled) return;
        setPreflight(report.data);
        setView(profile.data);
        setForm(formFromProfile(profile.data));
      })
      .catch(() => { if (!cancelled) setLoadError(true); });
    return () => { cancelled = true; };
  }, [sourceId]);

  const save = async () => {
    if (!form || !view) return;
    const result = profileFromForm(form, view.build_profile);
    if ('error' in result) {
      setSaveState({ kind: 'error', message: t(`settings.sourceProfile.formError.${result.error.field}`, { line: result.error.line ?? '' }) });
      return;
    }
    setSaveState({ kind: 'saving' });
    try {
      const saved = await api.putBuildProfile(sourceId, result.body);
      setView(saved.data);
      setForm(formFromProfile(saved.data));
      setSaveState({ kind: 'saved' });
    } catch (error) {
      setSaveState({ kind: 'error', message: errorText(error) ?? t('settings.sourceProfile.saveFailed') });
    }
  };

  const set = <K extends keyof ProfileForm>(key: K) => (value: ProfileForm[K]) => {
    setForm((current) => (current ? { ...current, [key]: value } : current));
    setSaveState(null);
  };

  return <>
    <div className="flex gap-1 px-5 pt-3" role="tablist">
      {(['preflight', 'profile'] as const).map((key) => (
        <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
          className={cn('rounded-md px-3 py-1.5 text-xs font-medium', tab === key ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-muted')}>
          {t(`settings.sourceProfile.tab.${key}`)}
        </button>
      ))}
    </div>
    <div className="min-h-0 flex-1 overflow-y-auto p-5 pt-3 text-xs">
      {loadError ? <p className="text-ds-red-500">{t('settings.sourceProfile.loadFailed')}</p>
        : !preflight || !form ? <p className="text-muted-foreground">{t('settings.sourceProfile.loading')}</p>
          : tab === 'preflight' ? <PreflightView report={preflight} />
            : <ProfileFormView form={form} set={set} canEdit={canEdit} />}
    </div>
    {tab === 'profile' && form && (
      <div className="flex items-center justify-end gap-3 border-t border-border px-5 py-3 text-xs">
        {saveState?.kind === 'saved' && <span className="text-ds-green-500">{t('settings.sourceProfile.saved')}</span>}
        {saveState?.kind === 'error' && <span className="text-ds-red-500" role="alert">{saveState.message}</span>}
        {!canEdit && <span className="text-muted-foreground">{t('settings.sourceProfile.adminOnly')}</span>}
        <button type="button" disabled={!canEdit || saveState?.kind === 'saving'} onClick={save}
          className="rounded-md bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          {t('settings.sourceProfile.save')}
        </button>
      </div>
    )}
  </>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="mt-4 first:mt-0">
    <h4 className="mb-1.5 text-[0.6875rem] font-bold uppercase tracking-wider text-muted-foreground">{title}</h4>
    {children}
  </section>;
}

function PreflightView({ report }: { report: PreflightReport }) {
  const { t } = useLanguage();
  const languages = Object.entries(report.files.by_language);
  return <>
    <Section title={t('settings.sourceProfile.hints')}>
      {report.hints.length ? <ul className="space-y-1.5">
        {report.hints.map((hint) => <li key={hint.code} className="rounded-md border border-ds-amber-500/30 bg-ds-amber-500/5 px-3 py-2">{hint.message}</li>)}
      </ul> : <p className="text-muted-foreground">{t('settings.sourceProfile.noHints')}</p>}
    </Section>
    <Section title={t('settings.sourceProfile.files', { total: report.files.total })}>
      <table className="w-full text-left">
        <thead className="text-muted-foreground"><tr>
          <th className="py-1 font-medium">{t('settings.sourceProfile.language')}</th>
          {STATUSES.map((status) => <th key={status} className="py-1 text-right font-medium">{t(`settings.sourceProfile.status.${status}`)}</th>)}
        </tr></thead>
        <tbody>{languages.map(([language, counts]) => <tr key={language} className="border-t border-border">
          <td className="py-1">{language}</td>
          {STATUSES.map((status) => <td key={status} className="py-1 text-right tabular-nums">{counts[status] || ''}</td>)}
        </tr>)}</tbody>
      </table>
      {Object.keys(report.files.encodings).length > 0 && <p className="mt-2 text-muted-foreground">
        {t('settings.sourceProfile.encodings')}: {Object.entries(report.files.encodings).map(([codec, count]) => `${codec} ${count}`).join(' · ')}
      </p>}
    </Section>
    {report.parser_gaps.length > 0 && <Section title={t('settings.sourceProfile.parserGaps')}>
      <table className="w-full text-left">
        <thead className="text-muted-foreground"><tr>
          <th className="py-1 font-medium">{t('settings.sourceProfile.pattern')}</th>
          <th className="py-1 text-right font-medium">{t('settings.sourceProfile.occurrences')}</th>
          <th className="py-1 text-right font-medium">{t('settings.sourceProfile.fileCount')}</th>
          <th className="py-1 pl-3 font-medium">{t('settings.sourceProfile.example')}</th>
        </tr></thead>
        <tbody>{report.parser_gaps.map((gap) => <tr key={gap.pattern} className="border-t border-border align-top">
          <td className="py-1 font-mono">{gap.pattern}</td>
          <td className="py-1 text-right tabular-nums">{gap.occurrences}</td>
          <td className="py-1 text-right tabular-nums">{gap.files}</td>
          <td className="break-all py-1 pl-3 font-mono text-muted-foreground">{gap.example}</td>
        </tr>)}</tbody>
      </table>
    </Section>}
    {(report.copybooks.ambiguous.length > 0 || report.copybooks.missing.length > 0) && <Section title={t('settings.sourceProfile.openCopies')}>
      <ul className="space-y-1">
        {report.copybooks.ambiguous.map((copy) => <li key={`a-${copy.name}`}>
          <span className="font-mono">{copy.name}</span> · {t('settings.sourceProfile.ambiguous', { count: copy.references })}
          <span className="block break-all font-mono text-muted-foreground">{copy.candidates.join(', ')}</span>
        </li>)}
        {report.copybooks.missing.map((copy) => <li key={`m-${copy.name}`}>
          <span className="font-mono">{copy.name}</span> · {t('settings.sourceProfile.missing', { count: copy.references })}
          <span className="ml-1 break-all font-mono text-muted-foreground">{copy.example_file}</span>
        </li>)}
      </ul>
    </Section>}
  </>;
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <label className="block">
    <span className="mb-1 block font-medium">{label}</span>
    {children}
    {hint && <span className="mt-0.5 block text-[0.6875rem] text-muted-foreground">{hint}</span>}
  </label>;
}

function ProfileFormView({ form, set, canEdit }: {
  form: ProfileForm;
  set: <K extends keyof ProfileForm>(key: K) => (value: ProfileForm[K]) => void;
  canEdit: boolean;
}) {
  const { t } = useLanguage();
  const text = (key: 'compiler_family' | 'compiler_version' | 'encoding') => ({
    value: form[key], disabled: !canEdit, className: input,
    onChange: (event: React.ChangeEvent<HTMLInputElement>) => set(key)(event.target.value),
  });
  const area = (key: 'defines' | 'copy_search_order' | 'language_paths' | 'paths_json', rows = 3) => ({
    value: form[key], disabled: !canEdit, rows, spellCheck: false, className: cn(input, 'font-mono'),
    onChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => set(key)(event.target.value),
  });
  return <div className="space-y-4">
    <p className="text-muted-foreground">{t('settings.sourceProfile.profileIntro')}</p>
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label={t('settings.sourceProfile.compilerFamily')}>
        <input list="doctus-compiler-families" placeholder="IBM_ENTERPRISE_COBOL" {...text('compiler_family')} />
        <datalist id="doctus-compiler-families">{COMPILER_FAMILIES.map((family) => <option key={family} value={family} />)}</datalist>
      </Field>
      <Field label={t('settings.sourceProfile.compilerVersion')}><input placeholder="6.4" {...text('compiler_version')} /></Field>
      <Field label={t('settings.sourceProfile.sourceFormat')}>
        <select value={form.source_format} disabled={!canEdit} onChange={(event) => set('source_format')(event.target.value)} className={input}>
          <option value="">{t('settings.sourceProfile.automatic')}</option>
          {SOURCE_FORMATS.map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
      </Field>
      <Field label={t('settings.sourceProfile.encoding')} hint={t('settings.sourceProfile.encodingHint')}>
        <input placeholder="CCSID-1141" {...text('encoding')} />
      </Field>
      <Field label={t('settings.sourceProfile.literalDelimiter')}>
        <select value={form.literal_delimiter} disabled={!canEdit} onChange={(event) => set('literal_delimiter')(event.target.value)} className={input}>
          <option value="">{t('settings.sourceProfile.automatic')}</option>
          {LITERAL_DELIMITERS.map((value) => <option key={value} value={value}>{t(`settings.sourceProfile.delimiter.${value}`)}</option>)}
        </select>
      </Field>
      <label className="flex items-center gap-2 self-end pb-1.5">
        <input type="checkbox" checked={form.debug_mode} disabled={!canEdit} onChange={(event) => set('debug_mode')(event.target.checked)} />
        <span>{t('settings.sourceProfile.debugMode')}</span>
      </label>
    </div>
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label={t('settings.sourceProfile.copySearchOrder')} hint={t('settings.sourceProfile.copySearchOrderHint')}>
        <textarea placeholder={'copy/team\ncopy/common'} {...area('copy_search_order')} />
      </Field>
      <Field label={t('settings.sourceProfile.defines')} hint={t('settings.sourceProfile.definesHint')}>
        <textarea placeholder="ENV=PROD" {...area('defines')} />
      </Field>
    </div>
    <Field label={t('settings.sourceProfile.languagePaths')} hint={t('settings.sourceProfile.languagePathsHint', { labels: LANGUAGE_LABELS.join(', ') })}>
      <textarea placeholder={'MEMBERS/COBOL = cobol\nMEMBERS/COPY = copybook'} {...area('language_paths')} />
    </Field>
    <details className="rounded-md border border-border px-3 py-2" open={Boolean(form.paths_json)}>
      <summary className="cursor-pointer font-medium">{t('settings.sourceProfile.pathOverrides')}</summary>
      <p className="my-1.5 text-muted-foreground">{t('settings.sourceProfile.pathOverridesHint')}</p>
      <textarea placeholder={'{\n  "legacy/os-vs": { "source_format": "fixed" }\n}'} {...area('paths_json', 5)} />
    </details>
  </div>;
}
