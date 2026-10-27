import * as Dialog from '@radix-ui/react-dialog';
import { Loader2, Play, SlidersHorizontal, X } from 'lucide-react';
import { useState, type Dispatch, type RefObject, type SetStateAction } from 'react';
import type { LlmProfile } from '@/hooks/useAiSettings';
import type { KnowledgeSource } from '@/types/domain';
import { LINK_RUN_OPTION_FIELDS, clampRunOption, type LinkRunOptions } from '@/lib/linkRunOptions';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

interface Props {
  open: boolean; onClose: () => void; isDark: boolean; projectName: string; isAdmin: boolean;
  returnFocusRef: RefObject<HTMLButtonElement>;
  minConfidence: number; onMinConfidence: (value: number) => void;
  maxItems: number; onMaxItems: (value: number) => void;
  runOptions: LinkRunOptions; setRunOptions: Dispatch<SetStateAction<LinkRunOptions>>;
  sources: KnowledgeSource[]; scopeIds: number[]; setScopeIds: Dispatch<SetStateAction<number[]>>;
  profiles: LlmProfile[]; activeProfileId?: string; onProfile?: (value: string) => void;
  onStart: () => Promise<boolean | undefined>;
  error?: string;
}

function AdvancedRunOptions({ runOptions, setRunOptions, inputClass }: Pick<Props, 'runOptions' | 'setRunOptions'> & { inputClass: string }) {
  const { t } = useLanguage();
  return <details data-testid="link-run-options" className="rounded-md border border-ds-zinc-500/25 p-3">
    <summary className="cursor-pointer text-sm font-medium"><SlidersHorizontal className="mr-2 inline h-4 w-4" />{t('linkManagerView.runOptions.label')}</summary>
    <p className="my-3 text-xs leading-relaxed text-ds-zinc-500">{t('linkManagerView.runOptions.hint')}</p>
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {LINK_RUN_OPTION_FIELDS.map(field => <label key={field.key} className="flex min-w-0 flex-col justify-between gap-1 text-xs">
        <span>{t(`linkManagerView.runOptions.${field.key}`)}</span>
        <input type="number" min={field.min} max={field.max} step={field.step}
          value={runOptions[field.key] ?? ''} placeholder={field.placeholder}
          onChange={event => {
            const value = event.target.value;
            setRunOptions(previous => {
              const next = { ...previous };
              if (value === '' || !Number.isFinite(Number(value))) delete next[field.key];
              else next[field.key] = clampRunOption(field, Number(value));
              return next;
            });
          }} className={inputClass} />
      </label>)}
    </div>
    <label className="mt-3 flex items-start gap-2 text-xs">
      <input type="checkbox" checked={Boolean(runOptions.dedupeByChunk)}
        onChange={event => setRunOptions(previous => ({ ...previous, dedupeByChunk: event.target.checked }))} />
      <span>{t('linkManagerView.runOptions.dedupeByChunk')}</span>
    </label>
    <button type="button" onClick={() => setRunOptions({})} className="mt-3 text-xs underline">{t('linkManagerView.runOptions.reset')}</button>
  </details>;
}

export function LinkAnalysisDialog(props: Props) {
  const { t } = useLanguage();
  const [starting, setStarting] = useState(false);
  const { open, onClose, isDark, minConfidence, onMinConfidence, maxItems, onMaxItems,
    profiles, activeProfileId, onProfile, sources, scopeIds, setScopeIds } = props;
  const inputClass = cn('h-9 min-w-0 w-full rounded-md border px-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-ds-indigo-400',
    isDark ? 'border-ds-zinc-700 bg-ds-zinc-800 text-ds-zinc-100' : 'border-ds-zinc-300 bg-ds-white text-ds-zinc-900');
  return <Dialog.Root open={open} onOpenChange={value => { if (!value && !starting) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-[110] bg-ds-black/65 backdrop-blur-sm" />
      <Dialog.Content data-testid="link-analysis-dialog"
        onCloseAutoFocus={event => { event.preventDefault(); props.returnFocusRef.current?.focus(); }}
        className={cn('fixed left-1/2 top-1/2 z-[111] flex max-h-[calc(100dvh_-_3rem)] w-[calc(100%_-_3rem)] max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-lg border shadow-2xl',
          isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-100' : 'border-ds-zinc-300 bg-ds-white text-ds-zinc-900')}>
        <div className="flex shrink-0 items-start gap-3 border-b border-ds-zinc-500/20 p-4">
          <div className="min-w-0 flex-1">
            <Dialog.Title className="text-sm font-semibold">{t('linkManagerView.analysis.title')}</Dialog.Title>
            <Dialog.Description className="mt-1 text-xs leading-relaxed text-ds-zinc-500">{t('linkManagerView.analysis.description')}</Dialog.Description>
            <p className="mt-2 truncate text-xs font-medium" title={props.projectName}>{props.projectName}</p>
          </div>
          <Dialog.Close disabled={starting} aria-label={t('linkManagerView.analysis.close')}
            className="shrink-0 rounded p-1 hover:bg-ds-zinc-500/15 disabled:opacity-40"><X className="h-4 w-4" /></Dialog.Close>
        </div>
        <div className="min-h-0 overflow-y-auto overscroll-contain p-4">
          {props.error && <p role="alert" className="mb-3 rounded border border-ds-amber-500/40 bg-ds-amber-500/10 p-3 text-xs">{props.error}</p>}
          <fieldset disabled={starting} className="space-y-4 disabled:opacity-60">
            {onProfile && profiles.length > 0 && <label className="block text-xs">
              <span className="mb-1 block">{t('chatView.selectModel')}</span>
              <Select value={activeProfileId} onValueChange={onProfile} disabled={starting}>
                <SelectTrigger className={inputClass} aria-label={t('chatView.selectModel')}><SelectValue /></SelectTrigger>
                <SelectContent className={cn('z-[120]', isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-100' : 'bg-ds-white text-ds-zinc-900')}>
                  {profiles.map(profile => <SelectItem key={profile.id} value={profile.id}>{profile.name} ({profile.model})</SelectItem>)}
                </SelectContent>
              </Select>
            </label>}
            <div className="grid grid-cols-2 gap-3">
              <label className="min-w-0 text-xs" title={t('linkManagerView.minConfidenceTooltip')}>
                <span className="mb-1 block">{t('linkManagerView.minConfidenceLabel')} (%)</span>
                <input aria-label={t('linkManagerView.minConfidenceLabel')} type="number" min={0} max={100} step={5}
                  value={minConfidence} onChange={event => onMinConfidence(Number(event.target.value))} className={inputClass} />
              </label>
              <label className="min-w-0 text-xs">
                <span className="mb-1 block">{t('linkManagerView.budget.label')}</span>
                <input type="number" min={1} max={5000} value={maxItems}
                  onChange={event => onMaxItems(Math.max(1, Math.min(5000, Number(event.target.value) || 1)))} className={inputClass} />
              </label>
            </div>
            <p className="text-xs leading-relaxed text-ds-zinc-500">{t('linkManagerView.budget.hint')}</p>
            {props.isAdmin && <fieldset className="min-w-0 rounded-md border border-ds-zinc-500/25 p-3">
              <legend className="px-1 text-xs font-medium">{t('linkManagerView.scopeLabel', { count: scopeIds.length })}</legend>
              <p className="mb-3 text-xs leading-relaxed text-ds-zinc-500">{t('linkManagerView.scopeHint')}</p>
              <div className="grid max-h-44 grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2">
                {sources.length ? sources.map(source => {
                  const id = Number(source.id);
                  return <label key={id} className="flex min-w-0 items-start gap-2 text-xs">
                    <input type="checkbox" checked={scopeIds.includes(id)} onChange={event => setScopeIds(previous => event.target.checked
                      ? [...previous, id] : previous.filter(value => value !== id))} />
                    <span className="min-w-0 break-words">{source.name || `#${id}`}</span>
                  </label>;
                }) : <p className="text-xs text-ds-zinc-500">{t('linkManagerView.scopeNoSources')}</p>}
              </div>
            </fieldset>}
            <AdvancedRunOptions runOptions={props.runOptions} setRunOptions={props.setRunOptions} inputClass={inputClass} />
          </fieldset>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-ds-zinc-500/20 p-4">
          <Dialog.Close disabled={starting} className="rounded-md px-3 py-2 text-xs hover:bg-ds-zinc-500/15 disabled:opacity-40">{t('linkManagerView.analysis.cancel')}</Dialog.Close>
          <button type="button" disabled={starting} onClick={async () => {
            setStarting(true);
            try { if (await props.onStart()) onClose(); }
            finally { setStarting(false); }
          }} className="flex items-center gap-2 rounded-md bg-ds-indigo-600 px-3 py-2 text-xs text-ds-white hover:bg-ds-indigo-550 disabled:opacity-40">
            {starting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}{t('linkManagerView.analysis.open')}
          </button>
        </div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
