"use client";

import { useMemo, useState } from 'react';
import type { CodeEntity } from '@/types/domain';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useEntityAnalysis } from '@/hooks/useEntityAnalysis';
import { pickFileLevelEntity } from '@/lib/entityAnchors';
import { getEntityTypeLabel } from '@/lib/graphTaxonomy';
import { cn } from '@/lib/utils';
import { MethodAnalysis } from './entity-analysis/MethodAnalysis';
import { MavenAnalysis } from './entity-analysis/MavenAnalysis';
import { FrameworkAnalysis } from './entity-analysis/FrameworkAnalysis';
import { record } from './entity-analysis/metadata';

interface Props {
  entity: CodeEntity | null | undefined;
  fileEntity: CodeEntity | null;
  entities: CodeEntity[];
  filePath: string | null;
  projectId?: number | null;
  theme: string;
  onOpenFile: (path: string, line: number | null, sourceId: number | string | null) => void;
}

export function EntityAnalysisDetails({ entity, fileEntity, entities, filePath, projectId, theme, onOpenFile }: Props) {
  const { t, language } = useLanguage();
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState<{ focus: number | undefined; id: number } | null>(null);
  const focus = entity?.file_path === filePath ? entity : fileEntity;
  const options = useMemo(() => {
    const choices = entities.filter(item => item.file_path === filePath && (focus?.source_id == null || String(item.source_id) === String(focus.source_id)) && (focus?.variant_key == null || item.variant_key === focus.variant_key));
    const all = new Map(choices.filter(item => item.id != null).map(item => [item.id, item]));
    if (focus?.id != null) all.set(focus.id, focus);
    return [...all.values()].sort((a, b) => (a.start_line || 0) - (b.start_line || 0));
  }, [entities, filePath, focus]);
  const current = choice && choice.focus === focus?.id ? options.find(item => item.id === choice.id) || focus : focus;
  const root = pickFileLevelEntity(options) || (fileEntity?.source_id === focus?.source_id ? fileEntity : null);
  const { analysis, loading } = useEntityAnalysis(open, current?.id, root?.id, projectId);
  if (current?.id == null) return null;
  const detail = analysis?.entity;
  const onOpen = (item: CodeEntity) => onOpenFile(item.file_path, item.start_line, item.source_id ?? null);
  return <details open={open} onToggle={event => setOpen(event.currentTarget.open)} className={cn('shrink-0 border-b border-ds-zinc-500/20 text-xs', theme === 'dark' ? 'bg-ds-zinc-950 text-ds-zinc-200' : 'bg-ds-white text-ds-zinc-800')}>
    <summary className="cursor-pointer px-4 py-2 font-semibold">{t('entityAnalysis.title')} · {current.name}</summary>
    <div className="max-h-[45vh] space-y-3 overflow-auto px-4 pb-3">
      <label className="flex items-center gap-2">{t('entityAnalysis.object')}<select aria-label={t('entityAnalysis.object')} className="min-w-0 max-w-full rounded border border-ds-zinc-500/40 bg-[rgb(var(--ds-surface))] px-2 py-1" value={current.id} onChange={event => setChoice({ focus: focus?.id, id: Number(event.target.value) })}>{options.map(item => <option key={item.id} value={item.id}>{item.name} · {getEntityTypeLabel(item.type, language)} · L{item.start_line}</option>)}</select></label>
      {loading && <p role="status">{t('entityAnalysis.loading')}</p>}
      {analysis?.failed && <p role="alert" className="text-ds-amber-500">{t('entityAnalysis.loadFailed')}</p>}
      {detail && <>
        <div className="flex flex-wrap items-baseline gap-2"><code className="break-words font-semibold">{detail.qualified_name || detail.name}</code><button type="button" className="text-ds-indigo-400 underline" onClick={() => onOpen(detail)}>{t('entityAnalysis.openSource')}</button></div>
        <MethodAnalysis meta={record(detail.meta)} onLine={line => onOpenFile(detail.file_path, line, detail.source_id ?? null)} />
        <FrameworkAnalysis meta={record(detail.meta)} neighbors={analysis?.neighbors || []} truncated={analysis?.linksTruncated || false} onOpen={onOpen} />
      </>}
      {analysis?.file && <MavenAnalysis meta={record(analysis.file.meta)} />}
    </div>
  </details>;
}
