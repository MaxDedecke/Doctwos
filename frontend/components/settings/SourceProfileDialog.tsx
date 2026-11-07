"use client";

import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, ClipboardCheck, Cpu, FileCode2, FileSearch, Files, FolderCog, FolderTree, Info, Library, Loader2, Save, ScanSearch, SlidersHorizontal, X } from 'lucide-react';
import React from 'react';
import { api } from '@/app/services/api';
import { selectTriggerClass } from '@/components/settings/formFields';
import { useSettings } from '@/components/settings/SettingsContext';
import {
  badgeClass, cardClass, dividerClass, emptyStateClass, ghostIconButtonClass, helpTextClass, inputClass,
  primaryButtonClass, sectionTitleClass, settingsRoot, strongTextClass,
} from '@/components/settings/settingsStyles';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
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

type Tab = 'preflight' | 'profile';
type SetField = <K extends keyof ProfileForm>(key: K) => (value: ProfileForm[K]) => void;

const COMPILER_FAMILIES = ['IBM_ENTERPRISE_COBOL', 'MICRO_FOCUS', 'GNUCOBOL', 'FUJITSU_COBOL2000'];
const STATUSES = ['complete', 'partial', 'text_fallback', 'skipped', 'error'] as const;
// Radix-Select kennt keinen leeren Wert; „automatisch“ steht für ein nicht gesetztes Feld.
const AUTO = 'auto';
const dark = (theme: string) => theme === 'dark';

function errorText(error: unknown): string | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' ? detail : null;
}

/** Buildprofil und Preflight-Bericht einer Git-Quelle: was wie gelesen wurde, wo die Analyse hakt, und die Einstellungen dazu. */
export function SourceProfileDialog({ source, canEdit, onClose }: Props) {
  const { t } = useLanguage();
  const { theme } = useSettings();
  return <Dialog.Root open={source !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-[110] bg-ds-black/80 backdrop-blur-sm" />
      <Dialog.Content data-testid="source-profile-dialog"
        className={cn(
          'fixed left-1/2 top-1/2 z-[111] flex max-h-[90vh] w-[calc(100%_-_1.5rem)] max-w-4xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-lg border shadow-2xl',
          dark(theme) ? 'bg-ds-zinc-900 border-ds-zinc-800/80 shadow-ds-black/80' : 'bg-ds-white border-ds-zinc-200 shadow-ds-zinc-300/80',
        )}>
        <header className={cn('flex items-start gap-3 border-b px-6 py-4', dark(theme) ? 'border-ds-zinc-800/60' : 'border-ds-zinc-200')}>
          <ClipboardCheck className="mt-0.5 h-4 w-4 shrink-0 text-ds-indigo-500" />
          <div className="min-w-0 flex-1 space-y-1">
            <Dialog.Title className={cn('text-xs font-extrabold uppercase tracking-wider', dark(theme) ? 'text-ds-zinc-100' : 'text-ds-zinc-800')}>
              {t('settings.sourceProfile.open')}
            </Dialog.Title>
            <p className={cn('truncate font-mono text-xs', strongTextClass(theme))}>{source?.name}</p>
            <Dialog.Description className={helpTextClass}>{t('settings.sourceProfile.description')}</Dialog.Description>
          </div>
          <Dialog.Close asChild>
            <Button type="button" variant="ghost" size="icon" aria-label={t('settings.sourceProfile.close')} className={ghostIconButtonClass}>
              <X className="h-4 w-4" />
            </Button>
          </Dialog.Close>
        </header>
        {source && <ProfileBody key={source.id} sourceId={source.id} canEdit={canEdit} />}
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}

function ProfileBody({ sourceId, canEdit }: { sourceId: number; canEdit: boolean }) {
  const { t } = useLanguage();
  const { theme } = useSettings();
  const [tab, setTab] = React.useState<Tab>('preflight');
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

  const set: SetField = (key) => (value) => {
    setForm((current) => (current ? { ...current, [key]: value } : current));
    setSaveState(null);
  };

  const tabs: { id: Tab; icon: React.ReactNode }[] = [
    { id: 'preflight', icon: <FileSearch className="h-3.5 w-3.5 shrink-0" /> },
    { id: 'profile', icon: <SlidersHorizontal className="h-3.5 w-3.5 shrink-0" /> },
  ];

  return <>
    <div role="tablist" className={cn('flex gap-1 border-b px-6 py-2', dark(theme) ? 'bg-ds-zinc-950/40 border-ds-zinc-800/60' : 'bg-ds-zinc-50 border-ds-zinc-200')}>
      {tabs.map(({ id, icon }) => (
        <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
          className={cn(
            'flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors duration-150',
            tab === id
              ? (dark(theme) ? 'bg-ds-indigo-500/10 text-ds-indigo-400 border-ds-indigo-500/20' : 'bg-ds-indigo-50 text-ds-indigo-700 border-ds-indigo-200/50')
              : (dark(theme) ? 'border-transparent text-ds-zinc-400 hover:bg-ds-zinc-800/40 hover:text-ds-zinc-200' : 'border-transparent text-ds-zinc-650 hover:bg-ds-zinc-200/55 hover:text-ds-zinc-900'),
          )}>
          {icon}{t(`settings.sourceProfile.tab.${id}`)}
        </button>
      ))}
    </div>
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
      {loadError ? <p role="alert" className={emptyStateClass(theme)}>{t('settings.sourceProfile.loadFailed')}</p>
        : !preflight || !form ? <p className="flex items-center gap-2 text-xs text-ds-zinc-500"><Loader2 className="h-3.5 w-3.5 animate-spin" />{t('settings.sourceProfile.loading')}</p>
          : tab === 'preflight' ? <PreflightView report={preflight} />
            : <ProfileFormView form={form} set={set} canEdit={canEdit} />}
    </div>
    {tab === 'profile' && form && (
      <footer className={cn('flex flex-wrap items-center justify-end gap-3 border-t px-6 py-4', dark(theme) ? 'bg-ds-zinc-950/20 border-ds-zinc-800/60' : 'bg-ds-zinc-50 border-ds-zinc-200')}>
        <div className="mr-auto min-w-0 text-xs">
          {saveState?.kind === 'saved' && <span className="font-semibold text-ds-emerald-600 dark:text-ds-emerald-400">{t('settings.sourceProfile.saved')}</span>}
          {saveState?.kind === 'error' && <span role="alert" className="font-semibold text-ds-red-600 dark:text-ds-red-400">{saveState.message}</span>}
          {!canEdit && <span className={helpTextClass}>{t('settings.sourceProfile.adminOnly')}</span>}
        </div>
        <Button type="button" disabled={!canEdit || saveState?.kind === 'saving'} onClick={save} className={primaryButtonClass}>
          {saveState?.kind === 'saving' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          {t('settings.sourceProfile.save')}
        </Button>
      </footer>
    )}
  </>;
}

function Stat({ label, value, caption, tone }: { label: string; value: string; caption?: string; tone?: 'warning' }) {
  const { theme } = useSettings();
  return <div className={cn(cardClass(theme), 'flex flex-col gap-1 px-4 py-3')}>
    <p className={labelClass}>{label}</p>
    <p className={cn('font-mono text-lg font-semibold tabular-nums', tone === 'warning' ? 'text-ds-amber-600 dark:text-ds-amber-400' : strongTextClass(theme))}>{value}</p>
    {caption && <p className={cn(helpTextClass, 'truncate')}>{caption}</p>}
  </div>;
}

/** Abschnitt wie in System & SSO: Icon und Überschrift über der Fläche. */
function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  const { theme } = useSettings();
  return <section className="space-y-3">
    <div className="flex items-center gap-1.5 text-ds-indigo-500">
      {icon}
      <h4 className={sectionTitleClass(theme)}>{title}</h4>
    </div>
    {children}
  </section>;
}

// Feldbeschriftung innerhalb einer Karte, eine Stufe unter der Abschnittsüberschrift (wie System & SSO).
const labelClass = 'block text-[0.625rem] font-bold uppercase tracking-wide text-ds-zinc-500';
const placeholderClass = 'placeholder:font-normal placeholder:text-ds-zinc-400 dark:placeholder:text-ds-zinc-600';

function Label({ text, children, hint }: { text: string; children: React.ReactNode; hint?: string }) {
  return <label className="block space-y-1.5">
    <span className={labelClass}>{text}</span>
    {children}
    {hint && <span className={cn(helpTextClass, 'block')}>{hint}</span>}
  </label>;
}

const tableClass = 'w-full text-left text-xs';
const headRowClass = 'border-b border-ds-zinc-200 dark:border-ds-zinc-800 text-ds-zinc-500';
const bodyClass = 'divide-y divide-ds-zinc-200/60 dark:divide-ds-zinc-800/60';

function PreflightView({ report }: { report: PreflightReport }) {
  const { t, language } = useLanguage();
  const { theme } = useSettings();
  const number = (value: number) => value.toLocaleString(language === 'de' ? 'de-DE' : 'en-US');
  const languages = Object.entries(report.files.by_language);
  const structured = languages.filter(([name]) => (LANGUAGE_LABELS as readonly string[]).includes(name));
  const structuredTotal = structured.reduce((sum, [, counts]) => sum + Object.values(counts).reduce((a, b) => a + b, 0), 0);
  const structuredComplete = structured.reduce((sum, [, counts]) => sum + (counts.complete ?? 0), 0);
  const openCopies = report.copybooks.ambiguous.length + report.copybooks.missing.length;
  // Bekannte Hinweise in der Sprache der Oberfläche; unbekannte Codes zeigen die Meldung des Servers.
  const hintText = (hint: PreflightReport['hints'][number]) => {
    const key = `settings.sourceProfile.hint.${hint.code}`;
    const text = t(key, { count: number(hint.count ?? 0) });
    return text === key ? hint.message : text;
  };

  return <div className={settingsRoot}>
    <div className="grid gap-3 sm:grid-cols-4">
      <Stat label={t('settings.sourceProfile.summaryFiles')} value={number(report.files.total)} />
      <Stat label={t('settings.sourceProfile.summaryComplete')}
        value={structuredTotal ? `${Math.round((structuredComplete / structuredTotal) * 100)} %` : '–'}
        caption={t('settings.sourceProfile.summaryCompleteCaption', { complete: number(structuredComplete), total: number(structuredTotal) })} />
      <Stat label={t('settings.sourceProfile.summaryGaps')} value={number(report.parser_gaps.length)} tone={report.parser_gaps.length ? 'warning' : undefined} />
      <Stat label={t('settings.sourceProfile.summaryOpenCopies')} value={number(openCopies)} tone={openCopies ? 'warning' : undefined} />
    </div>

    <Section icon={<Info className="h-3.5 w-3.5" />} title={t('settings.sourceProfile.hints')}>
      {report.hints.length ? <ul className="space-y-2">
        {report.hints.map((hint) => <li key={hint.code} className={cn(cardClass(theme), 'flex items-start gap-2.5 px-3.5 py-2.5 text-xs leading-relaxed')}>
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ds-amber-500" />
          <span className={dark(theme) ? 'text-ds-zinc-300' : 'text-ds-zinc-700'}>{hintText(hint)}</span>
        </li>)}
      </ul> : <p className={emptyStateClass(theme)}>{t('settings.sourceProfile.noHints')}</p>}
    </Section>

    <Section icon={<Files className="h-3.5 w-3.5" />} title={t('settings.sourceProfile.files')}>
      <div className={cn(cardClass(theme), 'overflow-x-auto px-4 py-3')}>
        <table className={tableClass}>
          <thead><tr className={headRowClass}>
            <th className="pb-2 font-semibold">{t('settings.sourceProfile.language')}</th>
            {STATUSES.map((status) => <th key={status} className="pb-2 text-right font-semibold">{t(`settings.sourceProfile.status.${status}`)}</th>)}
          </tr></thead>
          <tbody className={bodyClass}>{languages.map(([name, counts]) => <tr key={name}>
            <td className="py-1.5 font-mono">{name}</td>
            {STATUSES.map((status) => <td key={status} className={cn('py-1.5 text-right font-mono tabular-nums',
              counts[status] && status === 'partial' && 'text-ds-amber-600 dark:text-ds-amber-400',
              counts[status] && status === 'error' && 'text-ds-red-600 dark:text-ds-red-400')}>
              {counts[status] ? number(counts[status]) : <span className="text-ds-zinc-500">·</span>}
            </td>)}
          </tr>)}</tbody>
        </table>
        {Object.keys(report.files.encodings).length > 0 && <>
          <div className={cn(dividerClass(theme), 'my-3')} />
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={cn(labelClass, 'mr-1')}>{t('settings.sourceProfile.encodings')}</span>
            {Object.entries(report.files.encodings).map(([codec, count]) => (
              <span key={codec} className={cn(badgeClass('neutral'), 'font-mono normal-case tracking-normal')}>{codec} · {number(count)}</span>
            ))}
          </div>
        </>}
      </div>
    </Section>

    <Section icon={<ScanSearch className="h-3.5 w-3.5" />} title={t('settings.sourceProfile.parserGaps')}>
      {report.parser_gaps.length ? <div className={cn(cardClass(theme), 'overflow-x-auto px-4 py-3')}>
        <table className={tableClass}>
          <thead><tr className={headRowClass}>
            <th className="pb-2 font-semibold">{t('settings.sourceProfile.pattern')}</th>
            <th className="pb-2 text-right font-semibold">{t('settings.sourceProfile.occurrences')}</th>
            <th className="pb-2 text-right font-semibold">{t('settings.sourceProfile.fileCount')}</th>
            <th className="pb-2 pl-4 font-semibold">{t('settings.sourceProfile.example')}</th>
          </tr></thead>
          <tbody className={cn(bodyClass, 'font-mono')}>{report.parser_gaps.map((gap) => <tr key={gap.pattern} className="align-top">
            <td className="py-1.5">{gap.pattern}</td>
            <td className="py-1.5 text-right tabular-nums">{number(gap.occurrences)}</td>
            <td className="py-1.5 text-right tabular-nums">{number(gap.files)}</td>
            <td className="break-all py-1.5 pl-4 text-ds-zinc-500">{gap.example}</td>
          </tr>)}</tbody>
        </table>
      </div> : <p className={emptyStateClass(theme)}>{t('settings.sourceProfile.noGaps')}</p>}
    </Section>

    <Section icon={<Library className="h-3.5 w-3.5" />} title={t('settings.sourceProfile.openCopies')}>
      {openCopies ? <ul className={cn(cardClass(theme), 'divide-y px-4 text-xs', dark(theme) ? 'divide-ds-zinc-800/60' : 'divide-ds-zinc-200/60')}>
        {report.copybooks.ambiguous.map((copy) => <li key={`a-${copy.name}`} className="space-y-1 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className={cn('font-mono', strongTextClass(theme))}>{copy.name}</span>
            <span className={badgeClass('warning')}>{t('settings.sourceProfile.ambiguousBadge')}</span>
            <span className="text-ds-zinc-500">{t('settings.sourceProfile.references', { count: copy.references })}</span>
          </div>
          <p className="break-all font-mono text-[0.6875rem] text-ds-zinc-500">{copy.candidates.join(' · ')}</p>
        </li>)}
        {report.copybooks.missing.map((copy) => <li key={`m-${copy.name}`} className="space-y-1 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className={cn('font-mono', strongTextClass(theme))}>{copy.name}</span>
            <span className={badgeClass('neutral')}>{t('settings.sourceProfile.missingBadge')}</span>
            <span className="text-ds-zinc-500">{t('settings.sourceProfile.references', { count: copy.references })}</span>
          </div>
          <p className="break-all font-mono text-[0.6875rem] text-ds-zinc-500">{copy.example_file}</p>
        </li>)}
      </ul> : <p className={emptyStateClass(theme)}>{t('settings.sourceProfile.noOpenCopies')}</p>}
    </Section>
  </div>;
}

function Group({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  const { theme } = useSettings();
  return <Section icon={icon} title={title}>
    <div className={cn(cardClass(theme), 'space-y-3 p-4')}>{children}</div>
  </Section>;
}

function ProfileFormView({ form, set, canEdit }: { form: ProfileForm; set: SetField; canEdit: boolean }) {
  const { t } = useLanguage();
  const { theme } = useSettings();
  const textareaClass = cn(
    'w-full min-h-[76px] rounded-lg border px-3 py-2 font-mono text-xs outline-none transition-colors',
    dark(theme) ? 'bg-ds-zinc-950 border-ds-zinc-800 text-ds-zinc-100 focus:border-ds-zinc-700' : 'bg-ds-white border-ds-zinc-200 text-ds-zinc-800 focus:border-ds-zinc-300',
  );
  const selectContentClass = cn('z-[120]', dark(theme) ? 'bg-ds-zinc-900 border-ds-zinc-850 text-ds-zinc-200' : 'bg-ds-white border-ds-zinc-200 text-ds-zinc-800');
  const text = (key: 'compiler_family' | 'compiler_version' | 'encoding') => ({
    value: form[key], disabled: !canEdit, className: cn(inputClass(theme), placeholderClass, 'font-mono disabled:opacity-60'),
    onChange: (event: React.ChangeEvent<HTMLInputElement>) => set(key)(event.target.value),
  });
  const area = (key: 'defines' | 'copy_search_order' | 'language_paths' | 'paths_json') => ({
    value: form[key], disabled: !canEdit, spellCheck: false, className: cn(textareaClass, placeholderClass, 'disabled:opacity-60'),
    onChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => set(key)(event.target.value),
  });
  const example = (value: string) => `${t('settings.sourceProfile.eg')} ${value}`;
  const choice = (key: 'source_format' | 'literal_delimiter', values: readonly string[], label: (value: string) => string) => (
    <Select value={form[key] || AUTO} disabled={!canEdit} onValueChange={(value) => set(key)(value === AUTO ? '' : value)}>
      <SelectTrigger className={cn(selectTriggerClass, inputClass(theme))}><SelectValue /></SelectTrigger>
      <SelectContent className={selectContentClass}>
        <SelectItem value={AUTO} className="text-xs">{t('settings.sourceProfile.automatic')}</SelectItem>
        {values.map((value) => <SelectItem key={value} value={value} className="text-xs">{label(value)}</SelectItem>)}
      </SelectContent>
    </Select>
  );

  return <div className={settingsRoot}>
    <p className={helpTextClass}>{t('settings.sourceProfile.profileIntro')}</p>

    <Group icon={<Cpu className="h-3.5 w-3.5" />} title={t('settings.sourceProfile.groupCompiler')}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Label text={t('settings.sourceProfile.compilerFamily')}>
          <input list="doctus-compiler-families" placeholder={example('IBM_ENTERPRISE_COBOL')} {...text('compiler_family')} />
          <datalist id="doctus-compiler-families">{COMPILER_FAMILIES.map((family) => <option key={family} value={family} />)}</datalist>
        </Label>
        <Label text={t('settings.sourceProfile.compilerVersion')}><input placeholder={example('6.4')} {...text('compiler_version')} /></Label>
      </div>
    </Group>

    <Group icon={<FileCode2 className="h-3.5 w-3.5" />} title={t('settings.sourceProfile.groupSource')}>
      <div className="grid gap-3 sm:grid-cols-3">
        <Label text={t('settings.sourceProfile.sourceFormat')}>{choice('source_format', SOURCE_FORMATS, (value) => value)}</Label>
        <Label text={t('settings.sourceProfile.encoding')}><input placeholder={example('CCSID-1141')} {...text('encoding')} /></Label>
        <Label text={t('settings.sourceProfile.literalDelimiter')}>
          {choice('literal_delimiter', LITERAL_DELIMITERS, (value) => t(`settings.sourceProfile.delimiter.${value}`))}
        </Label>
      </div>
      <p className={helpTextClass}>{t('settings.sourceProfile.encodingHint')}</p>
      <label className="flex items-center gap-2 text-xs">
        <input type="checkbox" checked={form.debug_mode} disabled={!canEdit} onChange={(event) => set('debug_mode')(event.target.checked)} />
        <span className={dark(theme) ? 'text-ds-zinc-300' : 'text-ds-zinc-700'}>{t('settings.sourceProfile.debugMode')}</span>
      </label>
    </Group>

    <Group icon={<Library className="h-3.5 w-3.5" />} title={t('settings.sourceProfile.groupCopy')}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Label text={t('settings.sourceProfile.copySearchOrder')} hint={t('settings.sourceProfile.copySearchOrderHint')}>
          <Textarea placeholder={'copy/team\ncopy/common'} {...area('copy_search_order')} />
        </Label>
        <Label text={t('settings.sourceProfile.defines')} hint={t('settings.sourceProfile.definesHint')}>
          <Textarea placeholder="ENV=PROD" {...area('defines')} />
        </Label>
      </div>
    </Group>

    <Group icon={<FolderTree className="h-3.5 w-3.5" />} title={t('settings.sourceProfile.groupLanguage')}>
      <Label text={t('settings.sourceProfile.languagePaths')} hint={t('settings.sourceProfile.languagePathsHint', { labels: LANGUAGE_LABELS.join(', ') })}>
        <Textarea placeholder={'MEMBERS/COBOL = cobol\nMEMBERS/COPY = copybook'} {...area('language_paths')} />
      </Label>
    </Group>

    <Section icon={<FolderCog className="h-3.5 w-3.5" />} title={t('settings.sourceProfile.pathOverrides')}>
      <details className={cn(cardClass(theme), 'p-4')} open={Boolean(form.paths_json)}>
        <summary className={cn('cursor-pointer text-xs', strongTextClass(theme))}>{t('settings.sourceProfile.pathOverridesSummary')}</summary>
        <div className="mt-3 space-y-1.5">
          <p className={helpTextClass}>{t('settings.sourceProfile.pathOverridesHint')}</p>
          <Textarea aria-label={t('settings.sourceProfile.pathOverrides')} placeholder={'{\n  "legacy/os-vs": { "source_format": "fixed" }\n}'} {...area('paths_json')} />
        </div>
      </details>
    </Section>
  </div>;
}
