"use client";
import type { CodeEntity } from '@/types/domain';
import type { ForceGraphMethods, ForceGraphProps } from 'react-force-graph-2d';
import type { CallFlowData, CallFlowEdge } from '@/lib/callFlow';

import { api, API_URL } from '@/app/services/api';
import { ANALYSIS_STATUS_COLOR_TOKEN, formatAnalysisStatusTooltip, type AnalysisStatus } from '@/lib/analysisStatus';
import { getGraphEdgeColor } from '@/lib/graphTaxonomy';
import { resolveDsColor } from '@/lib/designTokens';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { AlertTriangle, Download, FileCode, Loader2, Maximize2, RefreshCw, ZoomIn, ZoomOut } from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { drawKnowledgeNodeIcon } from './KnowledgeNodeIcon';

export type CallNode = {
  id: string;
  entityId?: number;
  name: string;
  type: string;
  file_path?: string;
  start_line?: number | null;
  source_id?: number | string | null;
  unresolved?: boolean;
  // O-120: nur gesetzt, wenn die Datei dieses Knotens nicht uneingeschränkt
  // analysiert ist (siehe backend/core/analysis_status.py). Bewusst nur auf
  // Datei-Ebene -- welche Entities/Kanten genau unsicher sind, ist O-150s
  // Herkunfts-/Unsicherheitsvertrag, nicht Teil dieses Punkts.
  analysis_status?: AnalysisStatus;
  analysis_reasons?: string[];
  x?: number;
  y?: number;
};

export type CallEdge = {
  id: string;
  source: string | CallNode;
  target: string | CallNode;
  type: string;
  resolution: string;
  start_line?: number | null;
  meta?: CallFlowEdge['meta'];
};

interface Props {
  theme: string;
  focusedEntity: Pick<CodeEntity, 'id' | 'name'> | null;
  onFileSelect: (path: string, line?: number | null, sourceId?: number | string | null) => void;
  // Aktuell ausgewähltes Projekt (Workspace-weit) -- als Projekt-Kontext an
  // /callgraph/focus|export mitgeschickt, damit ein Fokus auf eine eigene
  // Projekt-Entity innerhalb dieses Projekts unverändert funktioniert. Fehlt es
  // (Allgemein-Modus) oder gehört die Entity zu einem ANDEREN Projekt, greift
  // serverseitig das Default-Deny-Opt-in (Project.expose_code_analysis_globally).
  projectId?: number | null;
  customFlow?: CallFlowData | null;
  onClearCustomFlow?: () => void;
}

export function CallGraphView({ theme, focusedEntity, onFileSelect, projectId, customFlow, onClearCustomFlow }: Props) {
  const { t } = useLanguage();
  const isDark = theme === 'dark';
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<ForceGraphMethods<CallNode, CallEdge> | undefined>(undefined);
  const [ForceGraph, setForceGraph] = useState<React.ComponentType<ForceGraphProps<CallNode, CallEdge> & { ref?: React.MutableRefObject<ForceGraphMethods<CallNode, CallEdge> | undefined> }> | null>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [hops, setHops] = useState(1);
  const [graph, setGraph] = useState<{ nodes: CallNode[]; edges: CallEdge[] }>({ nodes: [], edges: [] });
  const [availableTypes, setAvailableTypes] = useState<string[]>([]);
  const [enabledTypes, setEnabledTypes] = useState<Set<string>>(new Set());
  const [includeInheritance, setIncludeInheritance] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);

  useEffect(() => {
    import('react-force-graph-2d').then(mod => setForceGraph(() => mod.default));
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver(entries => {
      const rect = entries[0].contentRect;
      setDimensions({ width: Math.floor(rect.width), height: Math.floor(rect.height) });
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const effectiveEntity = customFlow?.root ? { id: customFlow.root.id, name: customFlow.root.name } : focusedEntity;

  useEffect(() => {
    if (!customFlow) return;
    queueMicrotask(() => {
      setLoading(false);
      setError(null);
      const nodes: CallNode[] = (customFlow.nodes || []).map((node) => ({
        id: `entity:${node.id}`,
        entityId: node.id,
        name: node.name,
        type: node.type || 'entity',
        file_path: node.file_path || undefined,
        start_line: node.start_line,
        source_id: node.source_id,
        analysis_status: node.analysis_status,
        analysis_reasons: node.analysis_reasons,
      }));
      const known = new Set(nodes.map(node => node.id));
      const edges: CallEdge[] = (customFlow.edges || []).map((edge) => {
        let target = edge.target == null ? `unresolved:${edge.id}` : `entity:${edge.target}`;
        if (!known.has(target)) {
          nodes.push({ id: target, name: edge.target_name, type: 'external', unresolved: true });
          known.add(target);
        }
        return {
          id: `edge:${edge.id}`,
          source: `entity:${edge.source}`,
          target,
          type: edge.type,
          resolution: edge.resolution,
          start_line: edge.start_line,
          meta: edge.meta,
        };
      });
      setGraph({ nodes, edges });
      const types = Array.from(new Set(edges.map(edge => edge.type))).sort();
      setAvailableTypes(types);
      setEnabledTypes(new Set(types));
      setTruncated(Boolean(customFlow.truncated));
      setTimeout(() => graphRef.current?.zoomToFit(350, 50), 100);
    });
  }, [customFlow]);

  const loadGraph = useCallback(async () => {
    if (customFlow) return;
    if (!effectiveEntity?.id) {
      setGraph({ nodes: [], edges: [] });
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const projectParam = projectId ? `&project_id=${projectId}` : '';
      const inheritanceParam = includeInheritance ? '&include_inheritance=true' : '';
      const response = await api.fetch(`${API_URL}/callgraph/focus?entity_id=${effectiveEntity.id}&hops=${hops}${projectParam}${inheritanceParam}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      type FocusNode = CodeEntity & { analysis_status?: AnalysisStatus; analysis_reasons?: string[] };
      const data: { nodes: FocusNode[]; edges: CallFlowEdge[]; edge_types?: string[]; truncated?: boolean } = await response.json();
      const nodes: CallNode[] = (data.nodes || []).map((node) => ({
        id: `entity:${node.id}`,
        entityId: node.id,
        name: node.name,
        type: node.type || 'entity',
        file_path: node.file_path,
        start_line: node.start_line,
        source_id: node.source_id,
        analysis_status: node.analysis_status,
        analysis_reasons: node.analysis_reasons,
      }));
      const known = new Set(nodes.map(node => node.id));
      const edges: CallEdge[] = (data.edges || []).map((edge) => {
        let target = edge.target == null ? `unresolved:${edge.id}` : `entity:${edge.target}`;
        if (!known.has(target)) {
          nodes.push({ id: target, name: edge.target_name, type: 'external', unresolved: true });
          known.add(target);
        }
        return {
          id: `edge:${edge.id}`,
          source: `entity:${edge.source}`,
          target,
          type: edge.type,
          resolution: edge.resolution,
          start_line: edge.start_line,
          meta: edge.meta,
        };
      });
      setGraph({ nodes, edges });
      const types = Array.from(new Set([
        ...(data.edge_types || []),
        ...edges.map(edge => edge.type),
      ])).sort();
      setAvailableTypes(types);
      setEnabledTypes(new Set(types));
      setTruncated(Boolean(data.truncated));
      setTimeout(() => graphRef.current?.zoomToFit(350, 50), 100);
    } catch (err) {
      setError((err instanceof Error ? err.message : undefined) || t('callGraphView.loadError'));
    } finally {
      setLoading(false);
    }
  }, [customFlow, effectiveEntity, hops, includeInheritance, projectId, t]);

  useEffect(() => {
    // queueMicrotask: loadGraph() sets loading/error state before its
    // first await, which reads as a synchronous setState-in-effect to the
    // compiler's analysis if called directly from the effect body.
    queueMicrotask(() => { loadGraph(); });
  }, [loadGraph]);

  const filtered = useMemo(() => {
    const links = graph.edges.filter(edge => enabledTypes.has(edge.type));
    const usedIds = new Set<string>([`entity:${effectiveEntity?.id}`]);
    links.forEach(edge => {
      usedIds.add(typeof edge.source === 'string' ? edge.source : edge.source.id);
      usedIds.add(typeof edge.target === 'string' ? edge.target : edge.target.id);
    });
    return { nodes: graph.nodes.filter(node => usedIds.has(node.id)), links };
  }, [graph, enabledTypes, effectiveEntity?.id]);

  const exportGraph = async (format: 'json' | 'csv' | 'graphml') => {
    if (customFlow && format === 'json') {
      const blob = new Blob([JSON.stringify(customFlow, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `callflow-${effectiveEntity?.name || 'export'}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      return;
    }
    if (!effectiveEntity?.id) return;
    const projectParam = projectId ? `&project_id=${projectId}` : '';
    const inheritanceParam = includeInheritance ? '&include_inheritance=true' : '';
    const response = await api.fetch(`${API_URL}/callgraph/export?entity_id=${effectiveEntity.id}&hops=${hops}&format=${format}${projectParam}${inheritanceParam}`);
    if (!response.ok) return setError(t('callGraphView.exportError', { status: response.status }));
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `callgraph-${effectiveEntity.name || effectiveEntity.id}.${format === 'graphml' ? 'graphml' : format}`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (!effectiveEntity?.id) {
    return <div className="h-full flex flex-col items-center justify-center gap-2 text-ds-zinc-500"><FileCode className="w-10 h-10 opacity-30" /><p className="text-sm">{t('callGraphView.focusFirst')}</p></div>;
  }

  return (
    <div className={cn('h-full flex flex-col', isDark ? 'bg-ds-zinc-950 text-ds-zinc-200' : 'bg-ds-white text-ds-zinc-800')}>
      <div className={cn('px-3 py-2 border-b flex flex-wrap items-center gap-2', isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200')}>
        <div className="min-w-0 mr-auto">
          <div className="text-xs font-bold truncate flex items-center gap-1.5">
            <span>{effectiveEntity.name}</span>
            {customFlow && (
              <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-ds-indigo-500/15 text-ds-indigo-400 border border-ds-indigo-500/30">
                {t('callGraphView.flowTitle')}
              </span>
            )}
          </div>
          <div className="text-[9px] uppercase tracking-wider text-ds-zinc-500">
            {customFlow ? (
              <>
                {customFlow.direction === 'outgoing'
                  ? t('callGraphView.flowDirectionOutgoing')
                  : customFlow.direction === 'incoming'
                    ? t('callGraphView.flowDirectionIncoming')
                    : t('callGraphView.flowDirectionBoth')} · {customFlow.hops} {customFlow.hops !== 1 ? t('callGraphView.hopUnitPlural') : t('callGraphView.hopUnit')} ({customFlow.nodes.length} Knoten)
              </>
            ) : (
              <>
                Call-Graph · {hops} {hops !== 1 ? t('callGraphView.hopUnitPlural') : t('callGraphView.hopUnit')}
              </>
            )}
          </div>
        </div>
        {customFlow && onClearCustomFlow && (
          <button
            type="button"
            onClick={onClearCustomFlow}
            className="h-7 px-2 rounded border border-ds-zinc-700 hover:border-ds-indigo-500 text-[10px] font-bold text-ds-zinc-400 hover:text-ds-indigo-400 transition-colors cursor-pointer"
            title={t('callGraphView.switchToFocusView')}
          >
            {t('callGraphView.switchToFocusView')}
          </button>
        )}
        {!customFlow && [1, 2, 3, 4, 5].map(value => <button key={value} onClick={() => setHops(value)} className={cn('h-7 px-2 rounded border text-[10px] font-bold', hops === value ? 'border-ds-indigo-500 bg-ds-indigo-500/15 text-ds-indigo-400' : 'border-ds-zinc-700 text-ds-zinc-500')}>{value} {t('callGraphView.hopUnit')}</button>)}
        <button onClick={loadGraph} title={t('callGraphView.reloadTitle')} className="p-1.5 text-ds-zinc-500 hover:text-ds-indigo-400 cursor-pointer"><RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} /></button>
        <button onClick={() => graphRef.current?.zoom(graphRef.current.zoom() * 1.3, 250)} title={t('callGraphView.zoomInTitle')} className="p-1.5 text-ds-zinc-500 hover:text-ds-indigo-400 cursor-pointer"><ZoomIn className="w-3.5 h-3.5" /></button>
        <button onClick={() => graphRef.current?.zoom(graphRef.current.zoom() / 1.3, 250)} title={t('callGraphView.zoomOutTitle')} className="p-1.5 text-ds-zinc-500 hover:text-ds-indigo-400 cursor-pointer"><ZoomOut className="w-3.5 h-3.5" /></button>
        <button onClick={() => graphRef.current?.zoomToFit(350, 50)} title={t('callGraphView.fitAllTitle')} className="p-1.5 text-ds-zinc-500 hover:text-ds-indigo-400 cursor-pointer"><Maximize2 className="w-3.5 h-3.5" /></button>
      </div>
      <div className={cn('px-3 py-1.5 border-b flex flex-wrap items-center gap-2', isDark ? 'border-ds-zinc-900' : 'border-ds-zinc-100')}>
        <button
          onClick={() => setIncludeInheritance(previous => !previous)}
          aria-pressed={includeInheritance}
          className={cn('px-2 py-1 rounded border text-[9px] font-bold', includeInheritance ? 'border-ds-indigo-500 bg-ds-indigo-500/15 text-ds-indigo-400' : 'border-ds-zinc-700 text-ds-zinc-500')}
        >{t('callGraphView.inheritanceLabel')}</button>
        {availableTypes.map(type => {
          const color = getGraphEdgeColor(type);
          return <button key={type} onClick={() => setEnabledTypes(previous => { const next = new Set(previous); next.has(type) ? next.delete(type) : next.add(type); return next; })} className={cn('px-2 py-1 rounded border text-[9px] font-bold', enabledTypes.has(type) ? 'opacity-100' : 'opacity-35')} style={{ borderColor: color, color }}>{type}</button>;
        })}
        <div className="ml-auto flex items-center gap-1">{(['json', 'csv', 'graphml'] as const).map(format => <button key={format} onClick={() => exportGraph(format)} className="flex items-center gap-1 px-2 py-1 text-[9px] uppercase font-bold text-ds-zinc-500 hover:text-ds-indigo-400"><Download className="w-3 h-3" />{format}</button>)}</div>
      </div>
      <div ref={containerRef} className="relative flex-1 min-h-0 overflow-hidden">
        {loading && <div className="absolute inset-0 z-10 flex items-center justify-center bg-ds-black/10"><Loader2 className="w-6 h-6 animate-spin text-ds-indigo-500" /></div>}
        {error && <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 px-3 py-2 rounded border border-ds-red-500/30 bg-ds-red-500/10 text-xs text-ds-red-400">{error}</div>}
        {truncated && <div className="absolute top-3 left-3 z-10 flex items-center gap-1 px-2 py-1 rounded border border-ds-amber-500/30 bg-ds-amber-500/10 text-[10px] text-ds-amber-400"><AlertTriangle className="w-3 h-3" />{t('callGraphView.truncatedNotice')}</div>}
        {!loading && filtered.nodes.length <= 1 && <div className="absolute inset-0 flex items-center justify-center text-xs text-ds-zinc-500">{t('callGraphView.noConnections')}</div>}
        {ForceGraph && dimensions.width > 0 && filtered.nodes.length > 0 && <ForceGraph
          ref={graphRef}
          graphData={filtered}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor={resolveDsColor(isDark ? 'rgb(var(--ds-neutral-950))' : 'rgb(var(--ds-white))')}
          nodeLabel={(node: CallNode) => {
            const base = `${node.name} (${node.type})`;
            return node.analysis_status
              ? `${base} — ${formatAnalysisStatusTooltip({ status: node.analysis_status, reasons: node.analysis_reasons || [] }, t)}`
              : base;
          }}
          nodeColor={(node: CallNode) => resolveDsColor(node.unresolved ? 'rgb(var(--ds-warning-base))' : node.entityId === effectiveEntity.id ? 'rgb(var(--ds-accent))' : 'rgb(var(--ds-info-base))')}
          nodeVal={(node: CallNode) => node.entityId === effectiveEntity.id ? 7 : 4}
          nodeCanvasObjectMode={() => 'replace'}
          nodeCanvasObject={(node: CallNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const radius = node.entityId === effectiveEntity.id ? 8 : 7;
            ctx.beginPath();
            ctx.arc(node.x ?? 0, node.y ?? 0, radius, 0, 2 * Math.PI);
            ctx.fillStyle = node.unresolved
              ? resolveDsColor('rgb(var(--ds-warning-base))')
              : node.entityId === effectiveEntity.id
                ? resolveDsColor('rgb(var(--ds-accent))')
                : resolveDsColor('rgb(var(--ds-info-base))');
            ctx.fill();
            // O-120: ein gestrichelter Ring markiert einen Knoten, dessen
            // Datei nicht uneingeschränkt analysiert ist -- dieselbe
            // Farbcodierung wie im Editor-Dateibaum/bei Chat-Zitaten.
            if (node.analysis_status) {
              ctx.save();
              ctx.setLineDash([2 / globalScale, 1.5 / globalScale]);
              ctx.lineWidth = 1.5 / globalScale;
              ctx.strokeStyle = resolveDsColor(ANALYSIS_STATUS_COLOR_TOKEN[node.analysis_status]);
              ctx.beginPath();
              ctx.arc(node.x ?? 0, node.y ?? 0, radius + 2.5 / globalScale, 0, 2 * Math.PI);
              ctx.stroke();
              ctx.restore();
            }
            drawKnowledgeNodeIcon({ ...node, type: node.unresolved ? 'external' : 'entity' }, ctx, globalScale);
            if (globalScale > 0.5) {
              const label = node.name ?? '';
              const maxLen = Math.min(18, Math.max(7, Math.floor(globalScale * 8)));
              const truncated = label.length > maxLen ? `${label.slice(0, maxLen)}…` : label;
              ctx.font = `${Math.min(11, 8 / globalScale * 1.8)}px Inter, system-ui, sans-serif`;
              ctx.textAlign = 'center';
              ctx.textBaseline = 'top';
              ctx.fillStyle = resolveDsColor(isDark ? 'rgb(var(--ds-neutral-200))' : 'rgb(var(--ds-neutral-600))');
              ctx.fillText(truncated, node.x ?? 0, (node.y ?? 0) + radius + 2 / globalScale);
            }
          }}
          linkColor={(edge: CallEdge) => resolveDsColor(edge.resolution === 'resolved' ? getGraphEdgeColor(edge.type) : 'rgb(var(--ds-warning-base))')}
          linkWidth={1.5}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          linkLineDash={(edge: CallEdge) => edge.resolution === 'resolved' ? null : [4, 3]}
          linkLabel={(edge: CallEdge) => `${edge.type} · ${edge.resolution}${edge.meta?.resolution_reason ? ` · ${edge.meta.resolution_reason}` : ''}`}
          onLinkClick={(edge: CallEdge) => {
            const source = typeof edge.source === 'string'
              ? graph.nodes.find(node => node.id === edge.source) : edge.source;
            if (source?.file_path) onFileSelect(source.file_path, edge.start_line ?? source.start_line, source.source_id);
          }}
          onNodeClick={(node: CallNode) => { if (!node.unresolved && node.file_path) onFileSelect(node.file_path, node.start_line, node.source_id); }}
        />}
      </div>
    </div>
  );
}
