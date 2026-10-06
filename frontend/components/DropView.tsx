"use client";
import type { CodeEntity } from '@/types/domain';

import { api } from '@/app/services/api';
import {
  DROP_DEFAULT_LAYERS, DROP_KINDS, DROP_MAX_LAYERS, layerWidthPercent, toggleExpanded, toggleKind,
  type DropDirection, type DropEdge, type DropKind, type DropNode, type DropResult,
} from '@/lib/dropView';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { AlertTriangle, ArrowDown, ArrowUp, ChevronsUpDown, Droplet, FileCode, Loader2, Target } from 'lucide-react';
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';

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

/** Farbe einer Verbindung nach Art: Daten cyan, Einbindung orange, Kontrollfluss blau. */
const EDGE_DATA = new Set(['READS', 'WRITES', 'USES', 'USES_DATASET', 'USES_TYPE', 'ASSIGNED_DATASET']);
const EDGE_INCLUDE = new Set(['COPY', 'INCLUDES', 'IMPORTS', 'EXTENDS', 'IMPLEMENTS', 'DEPENDS_ON']);
function edgeColor(type: string): string {
  if (EDGE_DATA.has(type)) return '#06b6d4';
  if (EDGE_INCLUDE.has(type)) return '#f59e0b';
  return '#6366f1';
}

interface Connector { key: string; d: string; color: string; from: number; to: number; reversed: boolean; type: string }

export function DropView({ theme, focusedEntity, projectId, onFileSelect }: Props) {
  const { t } = useLanguage();
  const isDark = theme === 'dark';
  const [startId, setStartId] = useState<number | null>(focusedEntity?.id ?? null);
  const [direction, setDirection] = useState<DropDirection>('down');
  const [kinds, setKinds] = useState<DropKind[]>(['control']);
  const [layers, setLayers] = useState(DROP_DEFAULT_LAYERS);
  const [expanded, setExpanded] = useState<number[]>([]);
  const [hoveredId, setHoveredId] = useState<number | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const nodeRefs = useRef<Map<number, HTMLElement>>(new Map());
  const [connectors, setConnectors] = useState<Connector[]>([]);

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
    <div key={node.id} data-testid={`drop-node-${node.id}`}
      ref={element => { if (element) nodeRefs.current.set(node.id, element); else nodeRefs.current.delete(node.id); }}
      onMouseEnter={() => setHoveredId(node.id)} onMouseLeave={() => setHoveredId(null)}
      className={cn(
      'group relative z-10 flex max-w-[16rem] items-center gap-1 rounded-md border px-2 py-1 text-[0.6875rem]',
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

  // Verbindungen zwischen den Ebenen: Kurven vom unteren Rand des oberen zum oberen Rand des unteren Knotens.
  const allEdges = useMemo<DropEdge[]>(() => {
    const seen = new Set<string>();
    const edges: DropEdge[] = [];
    for (const layer of result?.layers ?? []) {
      for (const edge of layer.edges ?? []) {
        const key = `${edge.from}>${edge.to}:${edge.type}`;
        if (!seen.has(key)) { seen.add(key); edges.push(edge); }
      }
    }
    return edges;
  }, [result]);

  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) { setConnectors([]); return; }
    const measure = () => {
      const base = canvas.getBoundingClientRect();
      const next: Connector[] = [];
      for (const edge of allEdges) {
        const a = nodeRefs.current.get(edge.from);
        const b = nodeRefs.current.get(edge.to);
        if (!a || !b) continue;
        const ra = a.getBoundingClientRect();
        const rb = b.getBoundingClientRect();
        // Oben/unten richtet sich nach der Lage, nicht nach der Kantenrichtung.
        const reversed = ra.top > rb.top;
        const upper = reversed ? rb : ra;
        const lower = reversed ? ra : rb;
        const x1 = upper.left + upper.width / 2 - base.left;
        const y1 = upper.bottom - base.top;
        const x2 = lower.left + lower.width / 2 - base.left;
        const y2 = lower.top - base.top;
        if (y2 <= y1) continue;
        const bend = (y2 - y1) / 2;
        next.push({
          key: `${edge.from}>${edge.to}:${edge.type}`,
          d: `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`,
          color: edgeColor(edge.type), from: edge.from, to: edge.to, reversed, type: edge.type,
        });
      }
      setConnectors(next);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [allEdges, expanded, result]);

  let body: React.ReactNode;
  if (startId == null) {
    body = <p className="p-6 text-center text-xs text-ds-zinc-500">{t('dropView.noFocus')}</p>;
  } else if (error) {
    body = <p role="alert" className="flex items-center justify-center gap-1 p-6 text-xs text-ds-red-400"><AlertTriangle className="h-3.5 w-3.5" aria-hidden />{t('dropView.loadError')}</p>;
  } else if (result) {
    const lastLayer = result.layers[result.layers.length - 1]?.layer ?? 0;
    body = (
      <div ref={canvasRef} className="relative flex flex-col items-center gap-8 p-4" data-testid="drop-pyramid">
        <svg className="pointer-events-none absolute inset-0 z-0 h-full w-full overflow-visible" aria-hidden="true" data-testid="drop-connectors">
          <defs>
            {['#6366f1', '#06b6d4', '#f59e0b'].map(color => (
              <marker key={color} id={`drop-arrow-${color.slice(1)}`} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L8,4 L0,8 z" fill={color} />
              </marker>
            ))}
          </defs>
          {connectors.map(connector => {
            const active = hoveredId == null || connector.from === hoveredId || connector.to === hoveredId;
            return (
              <path key={connector.key} d={connector.d} fill="none" stroke={connector.color}
                strokeWidth={active && hoveredId != null ? 2.5 : 1.5} strokeOpacity={active ? 0.85 : 0.12}
                markerEnd={connector.reversed ? undefined : `url(#drop-arrow-${connector.color.slice(1)})`}
                markerStart={connector.reversed ? `url(#drop-arrow-${connector.color.slice(1)})` : undefined}
                data-edge={connector.key}>
                <title>{connector.type}</title>
              </path>
            );
          })}
        </svg>
        {result.layers.map(layer => (
          <div key={layer.layer} data-testid={`drop-layer-${layer.layer}`} className="relative z-10 flex flex-col items-center gap-1" style={{ width: `${layerWidthPercent(layer.layer, Math.max(lastLayer, 1))}%` }}>
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
