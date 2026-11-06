import { SlidersHorizontal } from 'lucide-react';
import type { Dispatch, SetStateAction } from 'react';
import type { LlmProfile } from '@/hooks/useAiSettings';
import { LINK_RUN_OPTION_FIELDS, clampRunOption, type LinkRunOptions } from '@/lib/linkRunOptions';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

interface Props {
  isDark: boolean;
  inputClass: string;
  showEntityOptions: boolean;
  minConfidence: number; onMinConfidence: (value: number) => void;
  maxItems: number; onMaxItems: (value: number) => void;
  runOptions: LinkRunOptions; setRunOptions: Dispatch<SetStateAction<LinkRunOptions>>;
  profiles: LlmProfile[]; activeProfileId?: string; onProfile?: (value: string) => void;
}

function AdvancedRunOptions({ runOptions, setRunOptions, inputClass }: Pick<Props, 'runOptions' | 'setRunOptions' | 'inputClass'>) {
  const { t } = useLanguage();
  return <details data-testid="link-run-options" className="rounded-md border border-ds-zinc-500/25 p-3">
    <summary className="cursor-pointer text-sm font-medium"><SlidersHorizontal className="mr-2 inline h-4 w-4" />{t('linkManagerView.runOptions.label')}</summary>
    <p className="my-3 text-xs leading-relaxed text-ds-zinc-500">{t('linkManagerView.runOptions.hint')}</p>
    <div className="grid grid-cols-1 gap-3">
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

/** Modell, Mindest-Wahrscheinlichkeit, Budget und erweiterte Optionen des nächsten Laufs. */
export function LinkRunSettings(props: Props) {
  const { t } = useLanguage();
  const { isDark, inputClass, profiles, activeProfileId, onProfile } = props;
  return <section data-testid="link-run-settings" aria-label={t('linkManagerView.workspace.settingsTitle')}
    className="flex min-h-0 min-w-0 flex-col rounded-lg border border-ds-zinc-500/25">
    <header className="shrink-0 border-b border-ds-zinc-500/20 px-4 py-3">
      <h3 className="text-sm font-semibold">{t('linkManagerView.workspace.settingsTitle')}</h3>
    </header>
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
      {onProfile && profiles.length > 0 && <label className="block text-xs">
        <span className="mb-1 block">{t('chatView.selectModel')}</span>
        <Select value={activeProfileId} onValueChange={onProfile}>
          <SelectTrigger className={inputClass} aria-label={t('chatView.selectModel')}><SelectValue /></SelectTrigger>
          <SelectContent className={cn('z-[120]', isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-100' : 'bg-ds-white text-ds-zinc-900')}>
            {profiles.map(profile => <SelectItem key={profile.id} value={profile.id}>{profile.name} ({profile.model})</SelectItem>)}
          </SelectContent>
        </Select>
      </label>}
      <label className="block min-w-0 text-xs" title={t('linkManagerView.minConfidenceTooltip')}>
        <span className="mb-1 block">{t('linkManagerView.minConfidenceLabel')} (%)</span>
        <input aria-label={t('linkManagerView.minConfidenceLabel')} type="number" min={0} max={100} step={5}
          value={props.minConfidence} onChange={event => props.onMinConfidence(Number(event.target.value))} className={inputClass} />
      </label>
      <label className="block min-w-0 text-xs">
        <span className="mb-1 block">{t('linkManagerView.budget.label')}</span>
        <input type="number" min={1} max={5000} value={props.maxItems}
          onChange={event => props.onMaxItems(Math.max(1, Math.min(5000, Number(event.target.value) || 1)))} className={inputClass} />
      </label>
      <p className="text-xs leading-relaxed text-ds-zinc-500">{t('linkManagerView.budget.hint')}</p>
      {props.showEntityOptions && <AdvancedRunOptions runOptions={props.runOptions} setRunOptions={props.setRunOptions} inputClass={inputClass} />}
    </div>
  </section>;
}
