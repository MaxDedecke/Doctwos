import { CheckCircle2, FolderKanban, Link2, Loader2, Network, Play, Plus, RefreshCw, Search, Tag } from 'lucide-react';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import type { LinkCounts } from '@/lib/linkManagerTypes';
import type { LinkKindFilter } from '@/lib/linkRelationshipKind';
import type { RefObject } from 'react';

type Segment = 'links' | 'topics';
type Status = keyof LinkCounts;

interface ToolbarProps {
  projectName: string; hasProject: boolean; isDark: boolean; isAdmin: boolean;
  analysisTriggerRef: RefObject<HTMLButtonElement>;
  segment: Segment; onSegment: (segment: Segment) => void;
  isComputing: boolean; manualOpen: boolean;
  onAnalysis: () => void; onManual: () => void; onRefresh: () => void;
}

export function LinkManagerToolbar({ projectName, hasProject, analysisTriggerRef, isDark, isAdmin, segment, onSegment,
  isComputing, manualOpen, onAnalysis, onManual, onRefresh }: ToolbarProps) {
  const { t } = useLanguage();
  const button = 'flex h-8 w-8 shrink-0 items-center justify-center rounded-md disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ds-indigo-400 hover:bg-ds-zinc-500/15';
  return (
    <header data-testid="link-manager-toolbar" className={cn('shrink-0 border-b px-3 py-2 @lg/linkmgr:px-4',
      isDark ? 'border-ds-zinc-800 text-ds-zinc-100' : 'border-ds-zinc-200 text-ds-zinc-900')}>
      <div className="flex min-w-0 items-center gap-2">
        <Network className="h-4 w-4 shrink-0 text-ds-indigo-500" />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold">{t('linkManagerView.title')}</h2>
          <div title={projectName} className="flex min-w-0 items-center gap-1 text-xs text-ds-zinc-500">
            <FolderKanban className="h-3 w-3 shrink-0" /><span className="truncate">{projectName}</span>
          </div>
        </div>
        {segment === 'links' && <div className="flex shrink-0 items-center gap-1">
          <button ref={analysisTriggerRef} type="button" onClick={onAnalysis} disabled={isComputing || !hasProject}
            aria-label={t('linkManagerView.analysis.open')} title={t(isComputing ? 'linkManagerView.computingLabel' : 'linkManagerView.analysis.open')}
            className={cn(button, 'text-ds-indigo-500')}>
            {isComputing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          </button>
          <button type="button" onClick={onManual} disabled={!hasProject} aria-pressed={manualOpen}
            aria-label={t('linkManagerView.manualLabel')} title={t(hasProject ? 'linkManagerView.manualLabel' : 'linkManagerView.noProjectSelected')} className={button}>
            <Plus className="h-4 w-4" />
          </button>
          <button type="button" onClick={onRefresh} disabled={!hasProject} aria-label={t('linkManagerView.refreshLabel')}
            title={t('linkManagerView.refreshLabel')} className={button}><RefreshCw className="h-4 w-4" /></button>
        </div>}
        {isAdmin && <button type="button" onClick={() => onSegment(segment === 'links' ? 'topics' : 'links')}
          aria-label={t(`linkManagerView.segments.${segment === 'links' ? 'topics' : 'links'}`)}
          title={t(`linkManagerView.segments.${segment === 'links' ? 'topics' : 'links'}`)} className={button}>
          {segment === 'links' ? <Tag className="h-4 w-4" /> : <Link2 className="h-4 w-4" />}
        </button>}
      </div>

    </header>
  );
}

interface FiltersProps {
  isDark: boolean; status: Status; onStatus: (status: Status) => void; counts: LinkCounts;
  search: string; onSearch: (search: string) => void;
  minScore: number; onMinScore: (score: number) => void;
  kind: LinkKindFilter; onKind: (kind: LinkKindFilter) => void;
  perfectCount: number; isAccepting: boolean; onAcceptPerfect: () => void;
}

export function LinkManagerFilters({ isDark, status, onStatus, counts, search, onSearch,
  minScore, onMinScore, kind, onKind, perfectCount, isAccepting, onAcceptPerfect }: FiltersProps) {
  const { t } = useLanguage();
  const input = cn('h-8 min-w-0 rounded-md border px-2 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-ds-indigo-400',
    isDark ? 'border-ds-zinc-700 bg-ds-zinc-800 text-ds-zinc-200' : 'border-ds-zinc-300 bg-ds-white text-ds-zinc-900');
  const statuses: Status[] = ['pending', 'approved', 'rejected'];
  const kinds: LinkKindFilter[] = ['all', 'codeCode', 'codeDoc', 'docDoc'];
  return <section data-testid="link-manager-filters" aria-label={t('linkManagerView.filtersLabel')}
    className={cn('shrink-0 space-y-2 border-b px-3 py-2 @lg/linkmgr:px-4', isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200')}>
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <div className="hidden min-w-0 flex-wrap gap-1 @lg/linkmgr:flex">
        {statuses.map(value => <button key={value} onClick={() => onStatus(value)} aria-pressed={status === value}
          className={cn('flex items-center gap-1 rounded-md px-2 py-1.5 text-xs', status === value
            ? isDark ? 'bg-ds-zinc-700 text-ds-zinc-100' : 'bg-ds-zinc-200 text-ds-zinc-900' : 'text-ds-zinc-500 hover:bg-ds-zinc-500/10')}>
          {t(`linkManagerView.tabLabels.${value}`)}<span className="rounded bg-ds-zinc-500/15 px-1 text-xs">{counts[value]}</span>
        </button>)}
      </div>
      <select aria-label={t('linkManagerView.statusLabel')} value={status} onChange={event => onStatus(event.target.value as Status)}
        className={cn(input, 'max-w-full @lg/linkmgr:hidden')}>
        {statuses.map(value => <option key={value} value={value}>{t(`linkManagerView.tabLabels.${value}`)} ({counts[value]})</option>)}
      </select>
      <div className="relative min-w-0 flex-1 basis-32">
        <Search className="pointer-events-none absolute left-2 top-2.5 h-3 w-3 text-ds-zinc-500" />
        <input type="search" aria-label={t('linkManagerView.searchPlaceholder')} placeholder={t('linkManagerView.searchPlaceholder')}
          value={search} onChange={event => onSearch(event.target.value)} className={cn(input, 'w-full pl-7')} />
      </div>
    </div>
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <div className="hidden min-w-0 flex-wrap gap-1 @2xl/linkmgr:flex">
        {kinds.map(value => <button key={value} onClick={() => onKind(value)} aria-pressed={kind === value}
          className={cn('rounded-md border px-2 py-1.5 text-xs', kind === value
            ? 'border-ds-indigo-500/50 bg-ds-indigo-500/15 text-ds-indigo-500'
            : isDark ? 'border-ds-zinc-700 text-ds-zinc-400' : 'border-ds-zinc-300 text-ds-zinc-600')}>
          {t(`linkManagerView.kindFilter.${value}`)}
        </button>)}
      </div>
      <select aria-label={t('linkManagerView.relationshipLabel')} value={kind} onChange={event => onKind(event.target.value as LinkKindFilter)}
        className={cn(input, 'max-w-full flex-1 @2xl/linkmgr:hidden')}>
        {kinds.map(value => <option key={value} value={value}>{t(`linkManagerView.kindFilter.${value}`)}</option>)}
      </select>
      {status === 'pending' && <select aria-label={t('linkManagerView.scoreLabel')} value={minScore}
        onChange={event => onMinScore(Number(event.target.value))} className={cn(input, 'max-w-full')}>
        {[0, 60, 80].map(value => <option key={value} value={value}>{t(`linkManagerView.scoreFilter.${value ? `min${value}` : 'all'}`)}</option>)}
      </select>}
      {status === 'pending' && perfectCount > 0 && <button onClick={onAcceptPerfect} disabled={isAccepting}
        aria-label={`${t('linkManagerView.acceptAllLabel')} (${perfectCount})`} title={t('linkManagerView.acceptAllTooltip')}
        className="flex max-w-full items-center gap-1.5 rounded-md border border-ds-indigo-500/40 px-2 py-1.5 text-xs text-ds-indigo-500 disabled:opacity-40">
        {isAccepting ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />}
        <span className="hidden @xl/linkmgr:inline">{t('linkManagerView.acceptAllLabel')}</span><span>{perfectCount}</span>
      </button>}
    </div>
  </section>;
}
