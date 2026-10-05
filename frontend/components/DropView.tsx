"use client";
import type { CodeEntity } from '@/types/domain';

import { api } from '@/app/services/api';
import {
  DROP_DEFAULT_LAYERS, DROP_KINDS, DROP_MAX_LAYERS, layerWidthPercent, toggleExpanded, toggleKind,
  type DropDirection, type DropKind, type DropNode, type DropResult,
} from '@/lib/dropView';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { AlertTriangle, ArrowDown, ArrowUp, ChevronsUpDown, Droplet, FileCode, Loader2, Target } from 'lucide-react';
import React, { useEffect, useState } from 'react';

interface Props {
  theme: string;
  focusedEntity: Pick<CodeEntity, 'id' | 'name'> | null;
  projectId?: number | null;
  onFileSelect: (path: string, line?: number | null, sourceId?: number | string | null) => void;
}

const ROLE_STYLE: Record<string, string> = {
  container: 'border-ds-indigo-500/60',
  routine: 'border-ds-emerald-500/60',
  data: 'border-ds-amber-500/60',
};

export function DropView({ theme, focusedEntity, projectId, onFileSelect }: Props) {
  const { t } = useLanguage();
  const isDark = theme === 'dark';
  const [startId, setStartId] = useState<number | null>(focusedEntity?.id ?? null);
  const [direction, setDirection] = useState<DropDirection>('down');
  const [kinds, setKinds] = useState<DropKind[]>(['control']);
  const [layers, setLayers] = useState(DROP_DEFAULT_LAYERS);
  const [expanded, setExpanded] = useState<number[]>([]);

  // Jede Auswahl (Richtung, Kantenarten, Tiefe, geöffnete Ebenen) wird erst beim Umschalten geladen, nicht vorab.
  const requestKey = JSON.stringify([startId, projectId, direction, layers, kinds, expanded]);
  const [loaded, setLoaded] = useState<{ key: string; data: DropResult | null; failed: boolean } | null>(null);
  useEffect(() => {
    if (startId == null) return;
    let cancelled = false;
    api.getEntityDrop(startId, { projectId, direction, layers, kinds, expand: expanded })
      .then(response => { if (!cancelled) setLoaded({ key: requestKey, data: response.data, failed: false }); })
      .catch(() => { if (!cancelled) setLoaded({ key: requestKey, data: null, failed: true }); });
    return () => { cancelled = true; };
  }, [requestKey, startId, projectId, direction, layers, kinds, expanded]);
  const loading = startId != null && loaded?.key !== requestKey;
  const result = loaded?.data ?? null;
  const error = loaded?.key === requestKey && loaded.failed;

  const open = (node: DropNode) => onFileSelect(node.file_path, node.start_line, node.source_id);
  const restart = (node: DropNode) => { setStartId(node.id); setExpanded([]); };
  const chip = (node: DropNode, isRoot = false) => (
    <div key={node.id} data-testid={`drop-node-${node.id}`} className={cn(
      'group flex max-w-[16rem] items-center gap-1 rounded-md border px-2 py-1 text-[0.6875rem]',
      ROLE_STYLE[node.role ?? ''] ?? 'border-ds-zinc-500/60',
      isRoot ? 'border-2 font-semibold' : '',
      isDark ? 'bg-ds-zinc-900 text-ds-zinc-100' : 'bg-ds-white text-ds-zinc-900',
    )}>
      <button type="button" className="flex min-w-0 items-center gap-1 text-left" title={node.cite} onClick={() => open(node)}>
        <FileCode className="h-3 w-3 shrink-0 opacity-60" aria-hidden />
        <span className="truncate">{node.name}</span>
      </button>
      {!isRoot && (
        <button type="button" className="opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100" aria-label={t('dropView.restart', { name: node.name })} title={t('dropView.restart', { name: node.name })} onClick={() => restart(node)}>
          <Target className="h-3 w-3" aria-hidden />
        </button>
      )}
    </div>
  );

  const toolbar = (
    <div className={cn('flex shrink-0 flex-wrap items-center gap-2 border-b px-3 py-1.5 text-[0.6875rem]', isDark ? 'border-ds-zinc-800 bg-ds-zinc-950' : 'border-ds-zinc-200 bg-ds-white')}>
      <button type="button" aria-label={t(direction === 'down' ? 'dropView.showUp' : 'dropView.showDown')} title={t(direction === 'down' ? 'dropView.showUp' : 'dropView.showDown')}
        onClick={() => { setDirection(direction === 'down' ? 'up' : 'down'); setExpanded([]); }} className="rounded border border-ds-zinc-600/50 p-1">
        {direction === 'down' ? <ArrowDown className="h-3.5 w-3.5" aria-hidden /> : <ArrowUp className="h-3.5 w-3.5" aria-hidden />}
      </button>
      {DROP_KINDS.map(kind => (
        <button key={kind} type="button" aria-pressed={kinds.includes(kind)} onClick={() => { setKinds(toggleKind(kinds, kind)); setExpanded([]); }}
          className={cn('rounded-full border px-2 py-0.5', kinds.includes(kind) ? 'border-ds-indigo-500 text-ds-indigo-400' : 'border-ds-zinc-600/50 text-ds-zinc-500')}>
          {t(`dropView.kinds.${kind}`)}
        </button>
      ))}
      <label className="ml-auto flex items-center gap-1 text-ds-zinc-500">
        {t('dropView.layers')}
        <select value={layers} onChange={event => { setLayers(Number(event.target.value)); setExpanded([]); }} className="rounded border border-ds-zinc-600/50 bg-transparent px-1">
          {Array.from({ length: DROP_MAX_LAYERS }, (_, index) => index + 1).map(value => <option key={value} value={value}>{value}</option>)}
        </select>
      </label>
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-label={t('dropView.loading')} />}
    </div>
  );

  let body: React.ReactNode;
  if (startId == null) {
    body = <p className="p-6 text-center text-xs text-ds-zinc-500">{t('dropView.noFocus')}</p>;
  } else if (error) {
    body = <p role="alert" className="flex items-center justify-center gap-1 p-6 text-xs text-ds-red-400"><AlertTriangle className="h-3.5 w-3.5" aria-hidden />{t('dropView.loadError')}</p>;
  } else if (result) {
    const lastLayer = result.layers[result.layers.length - 1]?.layer ?? 0;
    body = (
      <div className="flex flex-col items-center gap-3 p-4" data-testid="drop-pyramid">
        {result.layers.map(layer => (
          <div key={layer.layer} data-testid={`drop-layer-${layer.layer}`} className="flex flex-col items-center gap-1" style={{ width: `${layerWidthPercent(layer.layer, Math.max(lastLayer, 1))}%` }}>
            {layer.layer > 0 && (
              <div className="flex items-center gap-2 text-[0.625rem] text-ds-zinc-500">
                <span>{t('dropView.layerLabel', { layer: layer.layer, count: layer.count })}</span>
                {layer.unresolved > 0 && <span title={t('dropView.unresolvedHint')}>{t('dropView.unresolved', { count: layer.unresolved })}</span>}
                {layer.truncated && <span>{t('dropView.truncated')}</span>}
              </div>
            )}
            {layer.collapsed ? (
              <button type="button" onClick={() => setExpanded(toggleExpanded(expanded, layer.layer))} className="flex items-center gap-1 rounded-md border border-dashed border-ds-zinc-500 px-3 py-1 text-[0.6875rem]">
                <ChevronsUpDown className="h-3 w-3" aria-hidden />{t('dropView.expand', { count: layer.count })}
              </button>
            ) : (
              <div className="flex flex-wrap justify-center gap-1.5">{layer.nodes.map(node => chip(node, layer.layer === 0))}</div>
            )}
          </div>
        ))}
        {result.stopped === 'end' && result.layers.length > 1 && <p className="text-[0.625rem] text-ds-zinc-500">{t('dropView.end')}</p>}
        {result.layers.length === 2 && result.layers[1].count === 0 && result.layers[1].unresolved === 0 && <p className="text-xs text-ds-zinc-500">{t('dropView.empty')}</p>}
      </div>
    );
  } else {
    body = null;
  }

  return (
    <div className="flex h-full flex-col" data-testid="drop-view">
      <div className="flex shrink-0 items-center gap-1 px-3 pt-2 text-[0.6875rem] font-semibold text-ds-zinc-500"><Droplet className="h-3 w-3" aria-hidden />{t('dropView.title')}</div>
      {toolbar}
      <div className="min-h-0 flex-1 overflow-auto">{body}</div>
    </div>
  );
}
