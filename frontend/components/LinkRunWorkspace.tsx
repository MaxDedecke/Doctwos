import * as Dialog from '@radix-ui/react-dialog';
import { ArrowLeftRight, Loader2, Play, X } from 'lucide-react';
import { useState, type RefObject } from 'react';
import type { LlmProfile } from '@/hooks/useAiSettings';
import { useLinkRunWorkspace } from '@/hooks/useLinkRunWorkspace';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { isEmptySet } from '@/lib/linkSets';
import { cn } from '@/lib/utils';
import { LinkRunSettings } from './LinkRunSettings';
import { LinkSetPanel, useLabel } from './LinkSetPanel';

interface Props {
  open: boolean;
  onClose: () => void;
  isDark: boolean;
  projectId: number;
  projectName: string;
  returnFocusRef: RefObject<HTMLButtonElement>;
  embeddingModel: string;
  profiles: LlmProfile[];
  activeProfileId?: string;
  onProfile?: (value: string) => void;
  /** Der Lauf ist angelegt; die Ansicht verfolgt ihn (Job Center, Fortschritt). */
  onStarted: (runId: number) => void;
}

/** Bildschirmbreite Arbeitsfläche für einen Analyse-Lauf: Menge A gegen Menge B, dazu die Laufeinstellungen. */
export function LinkRunWorkspace(props: Props) {
  const { t, language } = useLanguage();
  const label = useLabel();
  const { open, onClose, isDark, projectId } = props;
  const workspace = useLinkRunWorkspace(projectId, open, props.embeddingModel);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const number = (value: number) => value.toLocaleString(language === 'en' ? 'en-US' : 'de-DE');
  const inputClass = cn('h-9 min-w-0 w-full rounded-md border px-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-ds-indigo-400',
    isDark ? 'border-ds-zinc-700 bg-ds-zinc-800 text-ds-zinc-100' : 'border-ds-zinc-300 bg-ds-white text-ds-zinc-900');
  const { options, pairing, sets, estimate } = workspace;

  const emptySide = sets ? (isEmptySet(sets.a) ? 'a' : isEmptySet(sets.b) ? 'b' : null) : null;
  const summary = (() => {
    if (!sets) return null;
    if (emptySide) return t('linkManagerView.workspace.emptySet', { set: label(`linkManagerView.workspace.set.${emptySide}`, emptySide) });
    if (estimate.loading) return t('linkManagerView.workspace.estimating');
    if (estimate.error) return estimate.error;
    const data = estimate.data;
    if (!data) return null;
    const values = { a: number(data.a_count), b: number(data.b_count), reviews: number(data.reviews_max), budget: number(workspace.maxItems) };
    if (!data.targeted) return t(data.is_bootstrap ? 'linkManagerView.workspace.estimateBootstrap' : 'linkManagerView.workspace.estimateIncremental', values);
    return t('linkManagerView.workspace.estimateTargeted', values);
  })();

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      const result = await workspace.start();
      if (result.runId !== undefined) {
        props.onStarted(result.runId);
        onClose();
      } else {
        setError(result.error && result.error !== 'start' ? result.error : t('linkManagerView.budget.startFailed'));
      }
    } finally {
      setStarting(false);
    }
  };

  return <Dialog.Root open={open} onOpenChange={value => { if (!value && !starting) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-[110] bg-ds-black/65 backdrop-blur-sm" />
      <Dialog.Content data-testid="link-run-workspace" aria-describedby="link-run-workspace-description"
        onCloseAutoFocus={event => { event.preventDefault(); props.returnFocusRef.current?.focus(); }}
        className={cn('fixed inset-3 z-[111] flex flex-col overflow-hidden rounded-lg border shadow-2xl sm:inset-6',
          isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-100' : 'border-ds-zinc-300 bg-ds-white text-ds-zinc-900')}>
        <header className="flex shrink-0 flex-wrap items-start gap-x-6 gap-y-3 border-b border-ds-zinc-500/20 px-5 py-4">
          <div className="min-w-0 flex-1">
            <Dialog.Title className="text-base font-semibold">{t('linkManagerView.workspace.title')}</Dialog.Title>
            <Dialog.Description id="link-run-workspace-description" className="mt-1 max-w-3xl text-xs leading-relaxed text-ds-zinc-500">
              {t('linkManagerView.workspace.description')}
            </Dialog.Description>
            <p className="mt-1 truncate text-xs font-medium" title={props.projectName}>{props.projectName}</p>
          </div>
          {options && options.pairings.length > 1 && <div role="radiogroup" aria-label={t('linkManagerView.workspace.pairingLabel')}
            className="flex items-center gap-1 rounded-full border border-ds-zinc-500/25 p-1">
            {options.pairings.map(item => <button key={item.key} type="button" role="radio" aria-checked={pairing?.key === item.key}
              aria-label={`${label(`linkManagerView.workspace.kinds.${item.a}`, item.a)} ↔ ${label(`linkManagerView.workspace.kinds.${item.b}`, item.b)}`}
              onClick={() => workspace.setPairingKey(item.key)}
              className={cn('flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium',
                pairing?.key === item.key ? 'bg-ds-indigo-600 text-ds-white' : 'text-ds-zinc-500 hover:text-ds-zinc-200')}>
              {label(`linkManagerView.workspace.kinds.${item.a}`, item.a)}
              <ArrowLeftRight className="h-3 w-3" />
              {label(`linkManagerView.workspace.kinds.${item.b}`, item.b)}
            </button>)}
          </div>}
          <Dialog.Close disabled={starting} aria-label={t('linkManagerView.analysis.close')}
            className="shrink-0 rounded p-1 hover:bg-ds-zinc-500/15 disabled:opacity-40"><X className="h-4 w-4" /></Dialog.Close>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4 xl:overflow-hidden">
          {workspace.optionsError && <p role="alert" className="mb-3 rounded border border-ds-amber-500/40 bg-ds-amber-500/10 p-3 text-xs">{t('linkManagerView.workspace.optionsFailed')}</p>}
          {!sets || !pairing ? <p className="flex items-center gap-2 text-xs text-ds-zinc-500"><Loader2 className="h-4 w-4 animate-spin" />{t('linkManagerView.workspace.loading')}</p>
            : <fieldset disabled={starting} className="grid min-h-0 grid-cols-1 gap-4 disabled:opacity-60 lg:grid-cols-2 xl:h-full xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_20rem]">
              <LinkSetPanel side="a" projectId={projectId} set={sets.a} kindOptions={options?.kinds[sets.a.kind]} inputClass={inputClass}
                preview={workspace.previewA} onChange={change => workspace.updateSet('a', change)} />
              <LinkSetPanel side="b" projectId={projectId} set={sets.b} kindOptions={options?.kinds[sets.b.kind]} inputClass={inputClass}
                preview={workspace.previewB} onChange={change => workspace.updateSet('b', change)} />
              <div className="lg:col-span-2 xl:col-span-1 xl:min-h-0">
                <LinkRunSettings isDark={isDark} inputClass={inputClass} showEntityOptions={pairing.task_type === 'entity_links'}
                  minConfidence={workspace.minConfidence} onMinConfidence={workspace.setMinConfidence}
                  maxItems={workspace.maxItems} onMaxItems={workspace.setMaxItems}
                  runOptions={workspace.runOptions} setRunOptions={workspace.setRunOptions}
                  profiles={props.profiles} activeProfileId={props.activeProfileId} onProfile={props.onProfile} />
              </div>
            </fieldset>}
        </div>

        <footer className="flex shrink-0 flex-wrap items-center gap-3 border-t border-ds-zinc-500/20 px-5 py-3">
          <p className="min-w-0 flex-1 text-xs text-ds-zinc-500" aria-live="polite" data-testid="link-run-estimate">{summary}</p>
          {estimate.data?.has_active_run && <p className="text-xs text-ds-amber-500">{t('linkManagerView.workspace.activeRun')}</p>}
          {error && <p role="alert" className="text-xs text-ds-amber-500">{error}</p>}
          <Dialog.Close disabled={starting} className="rounded-md px-3 py-2 text-xs hover:bg-ds-zinc-500/15 disabled:opacity-40">{t('linkManagerView.analysis.cancel')}</Dialog.Close>
          <button type="button" disabled={starting || workspace.blocked} onClick={start}
            className="flex items-center gap-2 rounded-md bg-ds-indigo-600 px-3 py-2 text-xs text-ds-white hover:bg-ds-indigo-550 disabled:opacity-40">
            {starting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}{t('linkManagerView.workspace.start')}
          </button>
        </footer>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
