import * as Dialog from '@radix-ui/react-dialog';
import { ArrowLeftRight, Loader2, Play, Settings2, X } from 'lucide-react';
import { useState, type KeyboardEvent, type ReactNode, type RefObject } from 'react';
import type { LlmProfile } from '@/hooks/useAiSettings';
import { useLinkRunWorkspace } from '@/hooks/useLinkRunWorkspace';
import { useLinkSetLabels } from '@/hooks/useLinkSetLabels';
import { isEmptySet, type LinkSetDef, type SetPreview } from '@/lib/linkSets';
import { cn } from '@/lib/utils';
import { LinkRunSettings } from './LinkRunSettings';
import { LinkSetEditor } from './LinkSetEditor';

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

type Step = 'a' | 'b' | 'run';
const STEPS: Step[] = ['a', 'b', 'run'];

/** Übersichtskarte und Umschalter zugleich: zeigt, was eine Menge (oder der Lauf) gerade ausmacht. */
function StepCard({ step, active, onSelect, onKeyDown, eyebrow, headline, detail, warn, icon }: {
  step: Step; active: boolean; onSelect: () => void; onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void;
  eyebrow: string; headline: ReactNode; detail: string; warn?: boolean; icon?: ReactNode;
}) {
  return <button type="button" role="tab" id={`link-run-tab-${step}`} aria-selected={active} aria-controls="link-run-panel"
    tabIndex={active ? 0 : -1} onClick={onSelect} onKeyDown={onKeyDown}
    className={cn('flex min-w-0 flex-col items-start gap-1 rounded-lg border px-4 py-3 text-left transition-colors',
      'focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring',
      active ? 'border-primary bg-primary/10 shadow-sm' : 'border-border bg-card hover:border-primary/50')}>
    <span className="flex w-full items-center gap-2 text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">
      {icon}{eyebrow}
    </span>
    <span className="text-base font-semibold tabular-nums">{headline}</span>
    <span className={cn('w-full truncate text-xs', warn ? 'text-destructive' : 'text-muted-foreground')} title={detail}>{detail}</span>
  </button>;
}

/** Bildschirmbreite Arbeitsfläche für einen Analyse-Lauf: oben die Übersicht (Menge A ⇄ Menge B, Lauf), darunter genau
 *  eine Arbeitsfläche für die gewählte Karte, unten Aufwand und Start. */
export function LinkRunWorkspace(props: Props) {
  const labels = useLinkSetLabels();
  const { t, number } = labels;
  const { open, onClose, projectId } = props;
  const workspace = useLinkRunWorkspace(projectId, open, props.embeddingModel);
  const [step, setStep] = useState<Step>('a');
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputClass = cn('h-9 min-w-0 w-full rounded-md border border-input bg-background px-2.5 text-sm text-foreground',
    'focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring');
  const { options, pairing, sets, estimate } = workspace;
  const profile = props.profiles.find(item => item.id === props.activeProfileId);

  const emptySide = sets ? (isEmptySet(sets.a) ? 'a' : isEmptySet(sets.b) ? 'b' : null) : null;
  const summary = (() => {
    if (!sets) return null;
    if (emptySide) return t('linkManagerView.workspace.emptySet', { set: labels.setLabel(emptySide) });
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

  const moveFocus = (event: KeyboardEvent<HTMLButtonElement>) => {
    const index = STEPS.indexOf(step);
    const next = event.key === 'ArrowRight' ? STEPS[(index + 1) % STEPS.length]
      : event.key === 'ArrowLeft' ? STEPS[(index + STEPS.length - 1) % STEPS.length] : null;
    if (!next) return;
    event.preventDefault();
    setStep(next);
    document.getElementById(`link-run-tab-${next}`)?.focus();
  };

  const headline = (set: LinkSetDef, preview: { data: SetPreview | null; loading: boolean }) => {
    if (preview.loading || !preview.data) return <Loader2 aria-label={t('linkManagerView.workspace.estimating')} className="h-4 w-4 animate-spin text-muted-foreground" />;
    return set.kind === 'docs' && typeof preview.data.documents === 'number'
      ? t('linkManagerView.workspace.docCount', { count: number(preview.data.count), documents: number(preview.data.documents) })
      : t('linkManagerView.workspace.objectCount', { count: number(preview.data.count) });
  };

  return <Dialog.Root open={open} onOpenChange={value => { if (!value && !starting) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-[110] bg-ds-black/65 backdrop-blur-sm" />
      <Dialog.Content data-testid="link-run-workspace" aria-describedby="link-run-workspace-description"
        onCloseAutoFocus={event => { event.preventDefault(); props.returnFocusRef.current?.focus(); }}
        className="fixed inset-3 z-[111] flex flex-col overflow-hidden rounded-xl border border-border bg-background text-foreground shadow-2xl sm:inset-6">
        <header className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-3 border-b border-border px-5 py-3">
          <div className="min-w-0 flex-1">
            <Dialog.Title className="text-base font-semibold">{t('linkManagerView.workspace.title')}</Dialog.Title>
            <Dialog.Description id="link-run-workspace-description" className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{props.projectName}</span> · {t('linkManagerView.workspace.subtitle')}
            </Dialog.Description>
          </div>
          {options && options.pairings.length > 1 && <div role="radiogroup" aria-label={t('linkManagerView.workspace.pairingLabel')}
            className="inline-flex rounded-lg border border-border bg-muted p-1">
            {options.pairings.map(item => {
              const name = `${labels.kindLabel(item.a)} ↔ ${labels.kindLabel(item.b)}`;
              return <button key={item.key} type="button" role="radio" aria-checked={pairing?.key === item.key} aria-label={name}
                onClick={() => { workspace.setPairingKey(item.key); setStep('a'); }}
                className={cn('flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium',
                  pairing?.key === item.key ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground')}>
                {labels.kindLabel(item.a)}<ArrowLeftRight aria-hidden className="h-3 w-3" />{labels.kindLabel(item.b)}
              </button>;
            })}
          </div>}
          <Dialog.Close disabled={starting} aria-label={t('linkManagerView.analysis.close')}
            className="shrink-0 rounded-md p-1.5 hover:bg-muted disabled:opacity-40"><X className="h-4 w-4" /></Dialog.Close>
        </header>

        {workspace.optionsError && <p role="alert" className="mx-5 mt-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs">{t('linkManagerView.workspace.optionsFailed')}</p>}
        {!sets || !pairing ? <p className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />{t('linkManagerView.workspace.loading')}
        </p> : <fieldset disabled={starting} className="flex min-h-0 flex-1 flex-col disabled:opacity-60">
          <div role="tablist" aria-label={t('linkManagerView.workspace.tabsLabel')}
            className="grid shrink-0 grid-cols-1 items-stretch gap-3 px-5 pt-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_minmax(0,0.8fr)]">
            {(['a', 'b'] as const).map((side, index) => {
              const set = sets[side];
              const preview = side === 'a' ? workspace.previewA : workspace.previewB;
              const card = <StepCard key={side} step={side} active={step === side} onSelect={() => setStep(side)} onKeyDown={moveFocus}
                eyebrow={`${labels.setLabel(side)} · ${labels.kindLabel(set.kind)}`} headline={headline(set, preview)}
                detail={labels.summary(set, options?.kinds[set.kind])} warn={isEmptySet(set)} />;
              return index === 0 ? card : [
                <span key="against" aria-hidden className="hidden items-center justify-center text-muted-foreground md:flex" title={t('linkManagerView.workspace.checkedAgainst')}>
                  <ArrowLeftRight className="h-5 w-5" />
                </span>,
                card,
              ];
            })}
            <StepCard step="run" active={step === 'run'} onSelect={() => setStep('run')} onKeyDown={moveFocus}
              icon={<Settings2 aria-hidden className="h-3.5 w-3.5" />} eyebrow={t('linkManagerView.workspace.runCard')}
              headline={profile?.name ?? t('linkManagerView.workspace.runCardDefault')}
              detail={t('linkManagerView.workspace.runSummary', { confidence: workspace.minConfidence, budget: number(workspace.maxItems) })} />
          </div>

          <div id="link-run-panel" role="tabpanel" aria-labelledby={`link-run-tab-${step}`}
            className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-4 lg:overflow-hidden">
            {step === 'run'
              ? <div className="min-h-0 flex-1 lg:overflow-y-auto">
                <LinkRunSettings inputClass={inputClass} showEntityOptions={pairing.task_type === 'entity_links'}
                  minConfidence={workspace.minConfidence} onMinConfidence={workspace.setMinConfidence}
                  maxItems={workspace.maxItems} onMaxItems={workspace.setMaxItems}
                  runOptions={workspace.runOptions} setRunOptions={workspace.setRunOptions}
                  profiles={props.profiles} activeProfileId={props.activeProfileId} onProfile={props.onProfile} />
              </div>
              : <LinkSetEditor key={`${pairing.key}-${step}`} side={step} projectId={projectId} set={sets[step]}
                kindOptions={options?.kinds[sets[step].kind]} inputClass={inputClass}
                preview={step === 'a' ? workspace.previewA : workspace.previewB}
                onChange={change => workspace.updateSet(step, change)} />}
          </div>
        </fieldset>}

        <footer className="flex shrink-0 flex-wrap items-center gap-3 border-t border-border bg-card px-5 py-3">
          <p className="min-w-0 flex-1 text-xs text-muted-foreground" aria-live="polite" data-testid="link-run-estimate">{summary}</p>
          {estimate.data?.has_active_run && <p className="text-xs text-destructive">{t('linkManagerView.workspace.activeRun')}</p>}
          {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
          <Dialog.Close disabled={starting} className="rounded-md px-3 py-2 text-xs hover:bg-muted disabled:opacity-40">{t('linkManagerView.analysis.cancel')}</Dialog.Close>
          <button type="button" disabled={starting || workspace.blocked} onClick={start}
            className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40">
            {starting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}{t('linkManagerView.workspace.start')}
          </button>
        </footer>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
