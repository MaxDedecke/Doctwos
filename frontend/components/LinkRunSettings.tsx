import { ChevronRight } from 'lucide-react';
import { useState, type Dispatch, type SetStateAction } from 'react';
import type { LlmProfile } from '@/hooks/useAiSettings';
import { LINK_RUN_OPTION_FIELDS, clampRunOption, type LinkRunOptions } from '@/lib/linkRunOptions';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

interface Props {
  inputClass: string;
  showEntityOptions: boolean;
  minConfidence: number; onMinConfidence: (value: number) => void;
  maxItems: number; onMaxItems: (value: number) => void;
  runOptions: LinkRunOptions; setRunOptions: Dispatch<SetStateAction<LinkRunOptions>>;
  profiles: LlmProfile[]; activeProfileId?: string; onProfile?: (value: string) => void;
}

function AdvancedRunOptions({ runOptions, setRunOptions, inputClass }: Pick<Props, 'runOptions' | 'setRunOptions' | 'inputClass'>) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  return <section data-testid="link-run-options" className="rounded-lg border border-border bg-card">
    <button type="button" aria-expanded={open} onClick={() => setOpen(value => !value)}
      className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-medium">
      <ChevronRight aria-hidden className={cn('h-4 w-4 text-muted-foreground transition-transform', open && 'rotate-90')} />
      {t('linkManagerView.runOptions.label')}
    </button>
    {open && <div className="border-t border-border p-4">
      <p className="mb-4 text-xs leading-relaxed text-muted-foreground">{t('linkManagerView.runOptions.hint')}</p>
      <div className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
        {LINK_RUN_OPTION_FIELDS.map(field => <label key={field.key} className="flex min-w-0 flex-col justify-end gap-1 text-xs">
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
      <label className="mt-4 flex items-start gap-2 text-xs">
        <input type="checkbox" className="accent-primary" checked={Boolean(runOptions.dedupeByChunk)}
          onChange={event => setRunOptions(previous => ({ ...previous, dedupeByChunk: event.target.checked }))} />
        <span>{t('linkManagerView.runOptions.dedupeByChunk')}</span>
      </label>
      <button type="button" onClick={() => setRunOptions({})} className="mt-3 text-xs text-primary hover:underline">{t('linkManagerView.runOptions.reset')}</button>
    </div>}
  </section>;
}

/** Modell, Mindest-Wahrscheinlichkeit, Budget und erweiterte Optionen des nächsten Laufs. */
export function LinkRunSettings(props: Props) {
  const { t } = useLanguage();
  const { inputClass, profiles, activeProfileId, onProfile } = props;
  return <div data-testid="link-run-settings" className="mx-auto w-full max-w-3xl space-y-5">
    <div className="grid grid-cols-1 gap-4 rounded-lg border border-border bg-card p-4 sm:grid-cols-2">
      {onProfile && profiles.length > 0 && <label className="block text-xs sm:col-span-2">
        <span className="mb-1 block font-medium">{t('chatView.selectModel')}</span>
        <Select value={activeProfileId} onValueChange={onProfile}>
          <SelectTrigger className={inputClass} aria-label={t('chatView.selectModel')}><SelectValue /></SelectTrigger>
          <SelectContent className="z-[120] bg-popover text-popover-foreground">
            {profiles.map(profile => <SelectItem key={profile.id} value={profile.id}>{profile.name} ({profile.model})</SelectItem>)}
          </SelectContent>
        </Select>
      </label>}
      <label className="block min-w-0 text-xs" title={t('linkManagerView.minConfidenceTooltip')}>
        <span className="mb-1 block font-medium">{t('linkManagerView.minConfidenceLabel')} (%)</span>
        <input aria-label={t('linkManagerView.minConfidenceLabel')} type="number" min={0} max={100} step={5}
          value={props.minConfidence} onChange={event => props.onMinConfidence(Number(event.target.value))} className={inputClass} />
        <span className="mt-1 block leading-snug text-muted-foreground">{t('linkManagerView.workspace.confidenceHint')}</span>
      </label>
      <label className="block min-w-0 text-xs">
        <span className="mb-1 block font-medium">{t('linkManagerView.budget.label')}</span>
        <input type="number" min={1} max={5000} value={props.maxItems}
          onChange={event => props.onMaxItems(Math.max(1, Math.min(5000, Number(event.target.value) || 1)))} className={inputClass} />
        <span className="mt-1 block leading-snug text-muted-foreground">{t('linkManagerView.budget.hint')}</span>
      </label>
    </div>
    {props.showEntityOptions && <AdvancedRunOptions runOptions={props.runOptions} setRunOptions={props.setRunOptions} inputClass={inputClass} />}
  </div>;
}
