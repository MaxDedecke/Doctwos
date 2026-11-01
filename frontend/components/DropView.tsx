"use client";
import type { CodeEntity, WorkspaceDocument } from '@/types/domain';
import type { CallFlowData } from '@/lib/callFlow';

import { api } from '@/app/services/api';
import {
  DROP_DEFAULT_LAYERS, DROP_KINDS, DROP_MAX_LAYERS, citeLocation, connectorPath, flowToDrop, layerWidthPercent, nextZoom, sameLayerPath, toggleExpanded, toggleKind, ZOOM_MAX, ZOOM_MIN,
  type DropDirection, type DropEdge, type DropKind, type DropNode, type DropOrientation, type DropResult,
} from '@/lib/dropView';
import { ANALYSIS_STATUS_COLOR_TOKEN, formatAnalysisStatusTooltip } from '@/lib/analysisStatus';
import { getEdgeTypeLabel } from '@/lib/graphTaxonomy';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { dsColor } from '@/lib/designTokens';
import { cn } from '@/lib/utils';
import { AlertTriangle, ArrowDown, ArrowLeft, ArrowRight, ArrowUp, ChevronsUpDown, Columns3, FileCode, Layers, Loader2, Maximize2, Rows3, Target, Undo2, X, ZoomIn, ZoomOut, ExternalLink } from 'lucide-react';
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ChangePackageAction } from './ChangePackageAction';
import { InsightDraftAction } from './InsightDraftAction';
import { ProvenanceDisclosure } from './ProvenanceDisclosure';

interface Props {
  theme: string;
  focusedEntity: Pick<CodeEntity, 'id' | 'name'> | null;
  projectId?: number | null;
  onFileSelect: (path: string, line?: number | null, sourceId?: number | string | null) => void;
  onOpenDoc?: (filePath: string, sourceId: number | string | null, locator?: Partial<WorkspaceDocument>) => void;
  /** Ablauf oder Betroffenengraph aus dem Chat: wird statt der geladenen Ebenen gezeigt. */
  customFlow?: CallFlowData | null;
  onClearCustomFlow?: () => void;
}

const ROLE_STYLE: Record<string, string> = {
  container: 'border-ds-indigo-500/60',
  routine: 'border-ds-emerald-500/60',
  data: 'border-ds-amber-500/60',
};

/** Farbe einer Verbindung nach Art: Daten grün, Einbindung orange, Kontrollfluss blau. */
const EDGE_DATA = new Set(['READS', 'WRITES', 'USES', 'USES_DATASET', 'USES_TYPE', 'ASSIGNED_DATASET']);
const EDGE_INCLUDE = new Set(['COPY', 'INCLUDES', 'IMPORTS', 'EXTENDS', 'IMPLEMENTS', 'DEPENDS_ON']);
function edgeColor(type: string): string {
  if (EDGE_DATA.has(type)) return 'success-base';
  if (EDGE_INCLUDE.has(type)) return 'warning-base';
  return 'accent-base';
}

const ORIENTATION_STORAGE_KEY = 'doctus-drop-orientation';

function storedOrientation(): DropOrientation {
  try {
    return window.localStorage.getItem(ORIENTATION_STORAGE_KEY) === 'horizontal' ? 'horizontal' : 'vertical';
  } catch {
    return 'vertical';
  }
}

interface Connector { key: string; d: string; color: string; from: number; to: number; reversed: boolean; type: string; back: boolean }

const edgeKey = (edge: DropEdge) => `${edge.from}>${edge.to}:${edge.type}`;

export function DropView({ theme, focusedEntity, projectId, onFileSelect, onOpenDoc, customFlow, onClearCustomFlow }: Props) {
  const { t } = useLanguage();
  const isDark = theme === 'dark';
  const [startId, setStartId] = useState<number | null>(focusedEntity?.id ?? null);
  const [direction, setDirection] = useState<DropDirection>('down');
  const [kinds, setKinds] = useState<DropKind[]>(['control']);
  const [layers, setLayers] = useState(DROP_DEFAULT_LAYERS);
  const [orientation, setOrientation] = useState<DropOrientation>(storedOrientation);
  const horizontal = orientation === 'horizontal';
  const switchOrientation = () => {
    const next: DropOrientation = horizontal ? 'vertical' : 'horizontal';
    setOrientation(next);
    try {
      window.localStorage.setItem(ORIENTATION_STORAGE_KEY, next);
    } catch {
      // Ohne Speicher gilt die Wahl nur bis zum Neuladen.
    }
  };
  const [includeTests, setIncludeTests] = useState(false);
  const [expanded, setExpanded] = useState<number[]>([]);
  const [hoveredId, setHoveredId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(customFlow?.focus_entity_id ?? null);
  const [selectedEdgeKey, setSelectedEdgeKey] = useState<string | null>(null);
  const [history, setHistory] = useState<{ id: number; name: string }[]>([]);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const [zoom, setZoom] = useState(1);
  const zoomCenter = useRef<{ x: number; y: number } | null>(null);
  const nodeRefs = useRef<Map<number, HTMLElement>>(new Map());
  const [connectors, setConnectors] = useState<Connector[]>([]);

  // Der Start folgt dem Fokus, die Einstellungen bleiben. Ohne Fokus bleibt der Stand, wie in den anderen Ansichten.
  const focusId = focusedEntity?.id ?? null;
  const [seenFocus, setSeenFocus] = useState(focusId);
  if (focusId !== seenFocus) {
    setSeenFocus(focusId);
    if (focusId != null && focusId !== startId) {
      setStartId(focusId);
      setExpanded([]);
      setSelectedId(null);
      setSelectedEdgeKey(null);
      setHistory([]);
    }
  }
  // Eine Tour reicht je Schritt einen neuen Ablauf herein und zeigt damit auf ihren Knoten.
  const [seenFlow, setSeenFlow] = useState(customFlow);
  if (customFlow !== seenFlow) {
    setSeenFlow(customFlow);
    setSelectedId(customFlow?.focus_entity_id ?? null);
    setSelectedEdgeKey(null);
  }
  const isImpact = customFlow?.mode === 'impact';

  // Jede Auswahl (Richtung, Kantenarten, Tiefe, geöffnete Ebenen) wird erst beim Umschalten geladen, nicht vorab.
  const requestKey = JSON.stringify([startId, projectId, direction, layers, kinds, expanded, includeTests]);
  const [loaded, setLoaded] = useState<{ key: string; data: DropResult | null; failed: boolean } | null>(null);
  useEffect(() => {
    if (startId == null || customFlow) return;
    let cancelled = false;
    api.getEntityDrop(startId, { projectId, direction, layers, kinds, expand: expanded, includeTests })
      .then(response => { if (!cancelled) setLoaded({ key: requestKey, data: response.data, failed: false }); })
      .catch(() => { if (!cancelled) setLoaded({ key: requestKey, data: null, failed: true }); });
    return () => { cancelled = true; };
  }, [requestKey, startId, projectId, direction, layers, kinds, expanded, includeTests, customFlow]);
  const flowResult = useMemo(() => (customFlow ? flowToDrop(customFlow) : null), [customFlow]);
  const loading = !customFlow && startId != null && loaded?.key !== requestKey;
  const result = flowResult ?? loaded?.data ?? null;
  const error = !customFlow && loaded?.key === requestKey && loaded.failed;

  // Lauf eines gewählten Knotens: alles darüber bis zum Start und alles darunter, entlang der Verbindungen.
  const run = useMemo(() => {
    if (selectedId == null || !result) return null;
    const layerOf = new Map<number, number>();
    result.layers.forEach(layer => layer.nodes.forEach(node => layerOf.set(node.id, layer.layer)));
    if (!layerOf.has(selectedId)) return null;
    const edges: DropEdge[] = [];
    const seen = new Set<string>();
    for (const layer of result.layers) for (const edge of layer.edges ?? []) {
      const key = `${edge.from}>${edge.to}:${edge.type}`;
      if (!seen.has(key)) { seen.add(key); edges.push(edge); }
    }
    const nodes = new Set<number>([selectedId]);
    const keys = new Set<string>();
    for (const sign of [-1, 1]) {
      const queue = [selectedId];
      while (queue.length) {
        const current = queue.pop()!;
        for (const edge of edges) {
          const other = edge.from === current ? edge.to : edge.to === current ? edge.from : null;
          if (other == null || !layerOf.has(other)) continue;
          const delta = Math.sign((layerOf.get(other) ?? 0) - (layerOf.get(current) ?? 0));
          if (delta !== sign) continue;
          keys.add(`${edge.from}>${edge.to}:${edge.type}`);
          if (!nodes.has(other)) { nodes.add(other); queue.push(other); }
        }
      }
    }
    return { nodes, keys };
  }, [selectedId, result]);

  const open = (node: DropNode) => onFileSelect(node.file_path, node.start_line, node.source_id);
  const restart = (node: DropNode) => {
    if (result) setHistory(previous => [...previous, { id: result.root.id, name: result.root.name }]);
    setStartId(node.id); setExpanded([]); setSelectedId(null); setSelectedEdgeKey(null);
  };
  const goBack = () => {
    const previous = history[history.length - 1];
    if (!previous) return;
    setHistory(history.slice(0, -1));
    setStartId(previous.id); setExpanded([]); setSelectedId(null); setSelectedEdgeKey(null);
  };
  const select = (node: DropNode) => setSelectedId(previous => (previous === node.id ? null : node.id));
  const canOpen = (node: DropNode) => !isImpact && Boolean(node.file_path);
  const chip = (node: DropNode, isRoot = false) => (
    <div key={node.id} data-testid={`drop-node-${node.id}`}
      ref={element => { if (element) nodeRefs.current.set(node.id, element); else nodeRefs.current.delete(node.id); }}
      onMouseEnter={() => setHoveredId(node.id)} onMouseLeave={() => setHoveredId(null)}
      className={cn(
      'group relative z-10 flex max-w-[16rem] items-center gap-1 rounded-md border px-2 py-1 text-[0.6875rem]',
      ROLE_STYLE[node.role ?? ''] ?? 'border-ds-zinc-500/60',
      node.unresolved && 'border-dashed italic',
      isRoot ? 'border-2 font-semibold' : '',
      selectedId === node.id && 'ring-2 ring-ds-indigo-500/70',
      run && !run.nodes.has(node.id) && 'opacity-40',
      isDark ? 'bg-ds-zinc-900 text-ds-zinc-100' : 'bg-ds-white text-ds-zinc-900',
    )}>
      <button type="button" className="flex min-w-0 items-center gap-1 text-left" title={node.unresolved ? t('dropView.unresolvedNode') : node.cite} aria-pressed={selectedId === node.id} onClick={() => select(node)}>
        <FileCode className="h-3 w-3 shrink-0 opacity-60" aria-hidden />
        <span className="truncate">{node.name}</span>
        {node.analysis_status && (
          <span data-testid={`drop-node-status-${node.id}`} className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: dsColor(ANALYSIS_STATUS_COLOR_TOKEN[node.analysis_status]) }}
            title={formatAnalysisStatusTooltip({ status: node.analysis_status, reasons: node.analysis_reasons ?? [] }, t)} />
        )}
      </button>
      {canOpen(node) && (
        <button type="button" className="opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100" aria-label={t('dropView.openSource', { name: node.name })} title={t('dropView.openSource', { name: node.name })} onClick={() => open(node)}>
          <ExternalLink className="h-3 w-3" aria-hidden />
        </button>
      )}
      {!isRoot && !customFlow && (
        <button type="button" className="opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100" aria-label={t('dropView.restart', { name: node.name })} title={t('dropView.restart', { name: node.name })} onClick={() => restart(node)}>
          <Target className="h-3 w-3" aria-hidden />
        </button>
      )}
    </div>
  );

  // Beim Zoomen bleibt die Mitte des Ausschnitts in der Mitte, sonst springt man bei großen Läufen aus dem Bild.
  const changeZoom = (next: number) => {
    const scroller = scrollerRef.current;
    if (scroller && scroller.scrollWidth && scroller.scrollHeight) {
      zoomCenter.current = {
        x: (scroller.scrollLeft + scroller.clientWidth / 2) / scroller.scrollWidth,
        y: (scroller.scrollTop + scroller.clientHeight / 2) / scroller.scrollHeight,
      };
    }
    setZoom(next);
  };
  // Die größte Stufe, bei der nichts mehr übersteht. Sie wird gemessen, weil Ebenen beim Verkleinern anders umbrechen.
  const fitToView = () => {
    const scroller = scrollerRef.current;
    const canvas = canvasRef.current;
    if (!scroller || !canvas) return;
    const fits = (candidate: number) => {
      canvas.style.zoom = String(candidate);
      return scroller.scrollWidth <= scroller.clientWidth && scroller.scrollHeight <= scroller.clientHeight;
    };
    let best = ZOOM_MIN;
    if (fits(1)) {
      best = 1;
    } else {
      let low = ZOOM_MIN;
      let high = 1;
      for (let step = 0; step < 7; step += 1) {
        const middle = (low + high) / 2;
        if (fits(middle)) low = middle; else high = middle;
      }
      best = Math.round(low * 100) / 100;
    }
    canvas.style.zoom = String(best);
    zoomCenter.current = null;
    setZoom(best);
    scroller.scrollTo?.(0, 0);
  };
  useLayoutEffect(() => {
    const scroller = scrollerRef.current;
    const center = zoomCenter.current;
    zoomCenter.current = null;
    if (!scroller || !center) return;
    scroller.scrollLeft = center.x * scroller.scrollWidth - scroller.clientWidth / 2;
    scroller.scrollTop = center.y * scroller.scrollHeight - scroller.clientHeight / 2;
  }, [zoom]);

  const selectedNode = selectedId != null ? result?.layers.flatMap(layer => layer.nodes).find(node => node.id === selectedId && !node.unresolved) : undefined;
  const actionRoot = result?.root ?? (focusedEntity ? { id: focusedEntity.id, name: focusedEntity.name } : null);
  const actions = actionRoot && (
    <div className="ml-auto flex flex-wrap items-center gap-2">
      <ChangePackageAction
        projectId={projectId}
        target={selectedNode ? { entityId: selectedNode.id, sourceId: selectedNode.source_id, label: selectedNode.name } : { entityId: actionRoot.id, label: actionRoot.name }}
        theme={theme}
        onOpenCode={onFileSelect}
        onOpenDoc={onOpenDoc}
      />
      <InsightDraftAction
        projectId={projectId}
        origin="process"
        evidence={[{ entity_id: actionRoot.id, process_root: actionRoot.name }]}
        defaultTitle={actionRoot.name}
        theme={theme}
      />
    </div>
  );

  const toolbar = (
    <div className={cn('flex shrink-0 flex-wrap items-center gap-2 border-b px-3 py-1.5 text-[0.6875rem]', isDark ? 'border-ds-zinc-800 bg-ds-zinc-950' : 'border-ds-zinc-200 bg-ds-white')}>
      {history.length > 0 && !customFlow && (
        <button type="button" onClick={goBack} className="flex items-center gap-1 rounded border border-ds-zinc-600/50 px-1.5 py-0.5"
          aria-label={t('dropView.back', { name: history[history.length - 1].name })} title={t('dropView.back', { name: history[history.length - 1].name })}>
          <Undo2 className="h-3.5 w-3.5" aria-hidden /><span className="max-w-[10rem] truncate">{history[history.length - 1].name}</span>
        </button>
      )}
      {!customFlow && (
        <button type="button" aria-label={t(direction === 'down' ? 'dropView.showUp' : 'dropView.showDown')} title={t(direction === 'down' ? 'dropView.showUp' : 'dropView.showDown')}
          onClick={() => { setDirection(direction === 'down' ? 'up' : 'down'); setExpanded([]); }} className="rounded border border-ds-zinc-600/50 p-1">
          {direction === 'down'
            ? (horizontal ? <ArrowRight className="h-3.5 w-3.5" aria-hidden /> : <ArrowDown className="h-3.5 w-3.5" aria-hidden />)
            : (horizontal ? <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> : <ArrowUp className="h-3.5 w-3.5" aria-hidden />)}
        </button>
      )}
      <button type="button" aria-label={t(horizontal ? 'dropView.layoutVertical' : 'dropView.layoutHorizontal')} title={t(horizontal ? 'dropView.layoutVertical' : 'dropView.layoutHorizontal')}
        onClick={switchOrientation} className="rounded border border-ds-zinc-600/50 p-1">
        {horizontal ? <Rows3 className="h-3.5 w-3.5" aria-hidden /> : <Columns3 className="h-3.5 w-3.5" aria-hidden />}
      </button>
      {result && (
        <div className="flex items-center gap-0.5" role="group" aria-label={t('dropView.zoom')}>
          <button type="button" aria-label={t('dropView.zoomOut')} title={t('dropView.zoomOut')} disabled={zoom <= ZOOM_MIN} onClick={() => changeZoom(nextZoom(zoom, -1))} className="rounded border border-ds-zinc-600/50 p-1 disabled:opacity-40">
            <ZoomOut className="h-3.5 w-3.5" aria-hidden />
          </button>
          <button type="button" aria-label={t('dropView.zoomReset')} title={t('dropView.zoomReset')} onClick={() => changeZoom(1)} className="w-10 rounded py-0.5 text-center tabular-nums text-ds-zinc-500 hover:text-ds-indigo-400">
            {Math.round(zoom * 100)}%
          </button>
          <button type="button" aria-label={t('dropView.zoomIn')} title={t('dropView.zoomIn')} disabled={zoom >= ZOOM_MAX} onClick={() => changeZoom(nextZoom(zoom, 1))} className="rounded border border-ds-zinc-600/50 p-1 disabled:opacity-40">
            <ZoomIn className="h-3.5 w-3.5" aria-hidden />
          </button>
          <button type="button" aria-label={t('dropView.zoomFit')} title={t('dropView.zoomFit')} onClick={fitToView} className="ml-0.5 rounded border border-ds-zinc-600/50 p-1">
            <Maximize2 className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
      )}
      {!customFlow && DROP_KINDS.map(kind => (
        <button key={kind} type="button" aria-pressed={kinds.includes(kind)} onClick={() => { setKinds(toggleKind(kinds, kind)); setExpanded([]); }}
          className={cn('rounded-full border px-2 py-0.5', kinds.includes(kind) ? 'border-ds-indigo-500 text-ds-indigo-400' : 'border-ds-zinc-600/50 text-ds-zinc-500')}>
          {t(`dropView.kinds.${kind}`)}
        </button>
      ))}
      {!customFlow && (
        <button type="button" aria-pressed={includeTests} title={t('dropView.testsHint')} onClick={() => { setIncludeTests(!includeTests); setExpanded([]); }}
          className={cn('rounded-full border px-2 py-0.5', includeTests ? 'border-ds-indigo-500 text-ds-indigo-400' : 'border-ds-zinc-600/50 text-ds-zinc-500')}>
          {t('dropView.tests')}
        </button>
      )}
      {!customFlow && (
        <label className="ml-auto flex items-center gap-1 text-ds-zinc-500">
          {t('dropView.layers')}
          <select value={layers} onChange={event => { setLayers(Number(event.target.value)); setExpanded([]); }} className="rounded border border-ds-zinc-600/50 bg-transparent px-1">
            {Array.from({ length: DROP_MAX_LAYERS }, (_, index) => index + 1).map(value => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
      )}
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-label={t('dropView.loading')} />}
    </div>
  );

  // Verbindungen zwischen den Ebenen, gezeichnet von Rand zu Rand (siehe connectorPath); die Wege zurück gestrichelt.
  const allEdges = useMemo<(DropEdge & { back: boolean })[]>(() => {
    const seen = new Set<string>();
    const edges: (DropEdge & { back: boolean })[] = [];
    const add = (edge: DropEdge, back: boolean) => {
      const key = edgeKey(edge);
      if (!seen.has(key)) { seen.add(key); edges.push({ ...edge, back }); }
    };
    for (const layer of result?.layers ?? []) for (const edge of layer.edges ?? []) add(edge, false);
    for (const edge of result?.back_edges ?? []) add(edge, true);
    return edges;
  }, [result]);
  const nodeById = useMemo(() => new Map((result?.layers ?? []).flatMap(layer => layer.nodes).map(node => [node.id, node])), [result]);
  const selectedEdge = selectedEdgeKey != null ? allEdges.find(edge => edgeKey(edge) === selectedEdgeKey) : undefined;
  const tourEdge = customFlow?.highlighted_edge_id != null ? allEdges.find(edge => edge.id === customFlow.highlighted_edge_id) : undefined;
  const hasBackEdges = (result?.back_edges?.length ?? 0) > 0;

  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) { setConnectors([]); return; }
    const measure = () => {
      const base = canvas.getBoundingClientRect();
      // Die Linien liegen im selben gezoomten Bereich wie die Knoten, gemessen wird aber am Bildschirm.
      const scale = canvas.offsetWidth ? base.width / canvas.offsetWidth : 1;
      const local = (box: DOMRect) => ({
        left: (box.left - base.left) / scale, right: (box.right - base.left) / scale,
        top: (box.top - base.top) / scale, bottom: (box.bottom - base.top) / scale,
      });
      const origin = { left: 0, top: 0 };
      const next: Connector[] = [];
      for (const edge of allEdges) {
        const a = nodeRefs.current.get(edge.from);
        const b = nodeRefs.current.get(edge.to);
        if (!a || !b) continue;
        const boxA = local(a.getBoundingClientRect());
        const boxB = local(b.getBoundingClientRect());
        const path = edge.from === edge.to ? null : connectorPath(boxA, boxB, origin, orientation);
        next.push({
          key: edgeKey(edge),
          d: path?.d ?? sameLayerPath(boxA, boxB, origin, orientation),
          color: edgeColor(edge.type), from: edge.from, to: edge.to, reversed: path?.reversed ?? false, type: edge.type, back: edge.back,
        });
      }
      setConnectors(next);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [allEdges, expanded, result, orientation, zoom]);

  let body: React.ReactNode;
  if (startId == null && !customFlow) {
    body = <p className="p-6 text-center text-xs text-ds-zinc-500">{t('dropView.noFocus')}</p>;
  } else if (error) {
    body = <p role="alert" className="flex items-center justify-center gap-1 p-6 text-xs text-ds-red-400"><AlertTriangle className="h-3.5 w-3.5" aria-hidden />{t('dropView.loadError')}</p>;
  } else if (result) {
    const lastLayer = result.layers[result.layers.length - 1]?.layer ?? 0;
    const firstLayerEmpty = result.layers[1]?.count === 0;
    body = (
      <div ref={canvasRef} data-orientation={orientation} data-testid="drop-pyramid" style={{ zoom }}
        className={cn('relative flex p-4', horizontal ? 'min-h-full w-max min-w-full flex-row items-center gap-16' : 'flex-col items-center gap-8')}>
        <svg className="pointer-events-none absolute inset-0 z-0 h-full w-full overflow-visible" data-testid="drop-connectors">
          <defs>
            {['accent-base', 'success-base', 'warning-base'].map(color => (
              <marker key={color} id={`drop-arrow-${color}`} viewBox="0 0 8 8" refX="7" refY="4" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
                <path d="M0,0 L8,4 L0,8 z" fill={dsColor(color)} />
              </marker>
            ))}
          </defs>
          {connectors.map(connector => {
            const focus = run != null;
            const active = focus ? run.keys.has(connector.key) : hoveredId == null || connector.from === hoveredId || connector.to === hoveredId;
            const marked = selectedEdgeKey === connector.key || (tourEdge != null && edgeKey(tourEdge) === connector.key);
            const emphasized = marked || (focus ? active : active && hoveredId != null);
            const label = `${getEdgeTypeLabel(connector.type, t)}${connector.back ? ` · ${t('dropView.backEdge')}` : ''}`;
            return (
              <g key={connector.key}>
                <path d={connector.d} fill="none" stroke={dsColor(connector.color)}
                  strokeWidth={emphasized ? 2.5 : 1.5} strokeOpacity={active || marked ? 0.85 : 0.12} strokeDasharray={connector.back ? '4 3' : undefined}
                  markerEnd={connector.reversed ? undefined : `url(#drop-arrow-${connector.color})`}
                  markerStart={connector.reversed ? `url(#drop-arrow-${connector.color})` : undefined}
                  data-edge={connector.key} data-back={connector.back ? 'true' : undefined} data-marked={marked ? 'true' : undefined} />
                {!isImpact && (
                  <path d={connector.d} fill="none" stroke="transparent" strokeWidth={10} style={{ pointerEvents: 'stroke', cursor: 'pointer' }}
                    role="button" tabIndex={0} aria-label={t('dropView.edge.open', { label, from: nodeById.get(connector.from)?.name ?? '', to: nodeById.get(connector.to)?.name ?? '' })}
                    data-edge-hit={connector.key}
                    onClick={() => setSelectedEdgeKey(previous => (previous === connector.key ? null : connector.key))}
                    onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedEdgeKey(connector.key); } }}>
                    <title>{label}</title>
                  </path>
                )}
              </g>
            );
          })}
        </svg>
        {result.layers.map(layer => (
          <div key={layer.layer} data-testid={`drop-layer-${layer.layer}`} className="relative z-10 flex shrink-0 flex-col items-center gap-1" style={horizontal ? undefined : { width: `${layerWidthPercent(layer.layer, Math.max(lastLayer, 1))}%` }}>
            {layer.layer > 0 && (
              <div className="flex items-center gap-2 text-[0.625rem] text-ds-zinc-500">
                <span>{t('dropView.layerLabel', { layer: layer.layer, count: layer.count })}</span>
                {layer.unresolved > (layer.unresolved_external ?? 0) && <span title={t('dropView.unresolvedHint')}>{t('dropView.unresolved', { count: layer.unresolved - (layer.unresolved_external ?? 0) })}</span>}
                {(layer.unresolved_external ?? 0) > 0 && <span title={t('dropView.externalHint')}>{t('dropView.external', { count: layer.unresolved_external ?? 0 })}</span>}
                {layer.truncated && <span>{t('dropView.truncated')}</span>}
              </div>
            )}
            {layer.collapsed ? (
              <button type="button" onClick={() => setExpanded(toggleExpanded(expanded, layer.layer))} className="flex items-center gap-1 rounded-md border border-dashed border-ds-zinc-500 px-3 py-1 text-[0.6875rem]">
                <ChevronsUpDown className="h-3 w-3" aria-hidden />{t('dropView.expand', { count: layer.count })}
              </button>
            ) : (
              <div className={cn('flex gap-1.5', horizontal ? 'flex-col items-center' : 'flex-wrap justify-center')}>{layer.nodes.map(node => chip(node, layer.layer === 0))}</div>
            )}
          </div>
        ))}
        {customFlow && result.layers.length === 1 && <p className="text-xs text-ds-zinc-500">{t('dropView.empty')}</p>}
        {firstLayerEmpty && (result.alternatives?.length ?? 0) > 0 && (
          <div className="relative z-10 flex flex-wrap items-center justify-center gap-1.5 text-[0.6875rem]" data-testid="drop-alternatives">
            <span className="text-ds-zinc-500">{t('dropView.alternatives')}</span>
            {result.alternatives?.map(item => (
              <button key={`${item.direction}-${item.kind}`} type="button" onClick={() => { setDirection(item.direction); setKinds([item.kind]); setExpanded([]); }}
                className="rounded-full border border-ds-indigo-500/50 px-2 py-0.5 text-ds-indigo-400 hover:bg-ds-indigo-500/10">
                {t(item.direction === 'up' ? 'dropView.alternativeUp' : 'dropView.alternativeDown', { kind: t(`dropView.kinds.${item.kind}`), count: item.count })}
              </button>
            ))}
          </div>
        )}
        {!firstLayerEmpty && result.stopped === 'end' && result.layers.length > 1 && <p className="text-[0.625rem] text-ds-zinc-500">{t(horizontal ? 'dropView.endHorizontal' : 'dropView.end')}</p>}
        {result.layers.length === 2 && result.layers[1].count === 0 && result.layers[1].unresolved === 0 && <p className="text-xs text-ds-zinc-500">{t('dropView.empty')}</p>}
      </div>
    );
  } else {
    body = null;
  }

  const edgeLocation = selectedEdge ? citeLocation(selectedEdge.cite) : null;
  const edgeDetails = selectedEdge && !isImpact && (
    <section aria-label={t('dropView.edge.title')} data-testid="drop-edge-details"
      className={cn('max-h-[34%] min-h-[96px] shrink-0 overflow-y-auto border-t px-3 py-2.5', isDark ? 'border-ds-zinc-800 bg-ds-zinc-900/80' : 'border-ds-zinc-200 bg-ds-zinc-50')}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.6875rem] font-semibold">
            <span>{nodeById.get(selectedEdge.from)?.name}</span>
            <span className="text-ds-zinc-500" aria-hidden="true">→</span>
            <span>{nodeById.get(selectedEdge.to)?.name}</span>
            <span className="rounded border border-ds-zinc-600/50 px-1.5 py-0.5 text-[0.5625rem]">{getEdgeTypeLabel(selectedEdge.type, t)}</span>
            {selectedEdge.back && <span className="rounded border border-dashed border-ds-zinc-600/50 px-1.5 py-0.5 text-[0.5625rem]">{t('dropView.backEdge')}</span>}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[0.625rem] sm:grid-cols-3">
            <div><span className="text-ds-zinc-500">{t('dropView.edge.resolution')}: </span><span>{t(`callGraphView.resolution.${selectedEdge.resolution}`)}</span></div>
            <div><span className="text-ds-zinc-500">{t('dropView.edge.technicalType')}: </span><span className="font-mono">{selectedEdge.type}</span></div>
            {selectedEdge.condition && <div className="col-span-2 sm:col-span-3"><span className="text-ds-zinc-500">{t('dropView.edge.condition')}: </span><span className="break-words">{selectedEdge.condition}</span></div>}
            {selectedEdge.reason && <div className="col-span-2 sm:col-span-3"><span className="text-ds-zinc-500">{t('dropView.edge.reason')}: </span><span className="break-words">{selectedEdge.reason}</span></div>}
            <div className="col-span-2 font-mono text-ds-zinc-500 sm:col-span-3">{selectedEdge.cite && edgeLocation ? selectedEdge.cite : t('dropView.edge.sourceUnavailable')}</div>
          </div>
          <ProvenanceDisclosure provenance={selectedEdge.provenance} theme={theme} className="mt-2" />
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {edgeLocation && (
            <button type="button" onClick={() => onFileSelect(edgeLocation.path, edgeLocation.line, nodeById.get(selectedEdge.from)?.source_id)}
              className="inline-flex h-7 items-center gap-1.5 rounded border border-ds-indigo-500/50 px-2 text-[0.625rem] font-semibold text-ds-indigo-400 hover:bg-ds-indigo-500/10">
              <FileCode className="h-3 w-3" aria-hidden />{t('dropView.edge.openSource')}
            </button>
          )}
          <button type="button" onClick={() => setSelectedEdgeKey(null)} aria-label={t('dropView.edge.close')} className="rounded p-1 text-ds-zinc-500 hover:text-ds-zinc-200">
            <X className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
      </div>
    </section>
  );

  const flowBanner = customFlow && (
    <div className={cn('flex shrink-0 flex-wrap items-center gap-2 border-b px-3 py-1.5 text-[0.6875rem]', isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200')} data-testid="drop-flow-banner">
      <span className="font-bold">{customFlow.root.name}</span>
      <span className="rounded border border-ds-indigo-500/30 bg-ds-indigo-500/15 px-1.5 py-0.5 text-[0.5625rem] font-semibold text-ds-indigo-400">
        {t(isImpact ? 'callGraphView.impactTitle' : 'callGraphView.flowTitle')}
      </span>
      <span className="text-[0.5625rem] uppercase tracking-wider text-ds-zinc-500">
        {t(customFlow.direction === 'outgoing' ? 'callGraphView.flowDirectionOutgoing' : customFlow.direction === 'incoming' ? 'callGraphView.flowDirectionIncoming' : 'callGraphView.flowDirectionBoth')}
        {' · '}{customFlow.hops} {t(customFlow.hops !== 1 ? 'callGraphView.hopUnitPlural' : 'callGraphView.hopUnit')}
      </span>
      {customFlow.truncated && <span className="flex items-center gap-1 text-ds-amber-400"><AlertTriangle className="h-3 w-3" aria-hidden />{t('dropView.flowTruncated')}</span>}
      {onClearCustomFlow && (
        <button type="button" onClick={onClearCustomFlow} className="ml-auto h-6 rounded border border-ds-zinc-600/50 px-2 text-[0.625rem] font-bold text-ds-zinc-400 hover:border-ds-indigo-500 hover:text-ds-indigo-400">
          {t('callGraphView.switchToFocusView')}
        </button>
      )}
    </div>
  );

  return (
    <div className="flex h-full flex-col" data-testid="drop-view">
      <div className="flex shrink-0 flex-wrap items-center gap-1 px-3 pt-2 text-[0.6875rem] font-semibold text-ds-zinc-500"><Layers className="h-3 w-3" aria-hidden />{t(customFlow ? 'dropView.titleFlow' : 'dropView.title')}{actions}</div>
      {flowBanner}
      {toolbar}
      <div ref={scrollerRef} className="min-h-0 flex-1 overflow-auto">{body}</div>
      {hasBackEdges && <p className="shrink-0 px-3 py-1 text-[0.625rem] text-ds-zinc-500">{t('dropView.backEdgeHint')}</p>}
      {edgeDetails}
    </div>
  );
}
