"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Download, FileCode, Loader2, Maximize2, RefreshCw, ZoomIn, ZoomOut } from 'lucide-react';
import { API_URL } from '@/app/services/api';
import { cn } from '@/lib/utils';
import { resolveDsColor } from '@/lib/designTokens';
import { useLanguage } from '@/lib/i18n/LanguageContext';

type CallNode = {
  id: string;
  entityId?: number;
  name: string;
  type: string;
  file_path?: string;
  start_line?: number;
  source_id?: number | null;
  unresolved?: boolean;
  x?: number;
  y?: number;
};

type CallEdge = {
  id: string;
  source: string | CallNode;
  target: string | CallNode;
  type: 'CALL' | 'PERFORM' | 'GOTO' | 'COPY' | 'CONTAINS';
  resolution: string;
};

const EDGE_COLORS: Record<string, string> = {
  CALL: 'rgb(var(--ds-danger-base))',
  PERFORM: 'rgb(var(--ds-success-base))',
  GOTO: 'rgb(var(--ds-warning-base))',
  COPY: 'rgb(var(--ds-graph-a-base))',
  CONTAINS: 'rgb(var(--ds-graph-b-base))',
};

interface Props {
  theme: string;
  focusedEntity: any | null;
  onFileSelect: (path: string, line?: number | null, sourceId?: number | string | null) => void;
  // Aktuell ausgewähltes Projekt (Workspace-weit) -- als Projekt-Kontext an
  // /callgraph/focus|export mitgeschickt, damit ein Fokus auf eine eigene
  // Projekt-Entity innerhalb dieses Projekts unverändert funktioniert. Fehlt es
  // (Allgemein-Modus) oder gehört die Entity zu einem ANDEREN Projekt, greift
  // serverseitig das Default-Deny-Opt-in (Project.expose_code_analysis_globally).
  projectId?: number | null;
}

export function CallGraphView({ theme, focusedEntity, onFileSelect, projectId }: Props) {
  const { t } = useLanguage();
  const isDark = theme === 'dark';
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);
  const [ForceGraph, setForceGraph] = useState<any>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [hops, setHops] = useState(1);
  const [graph, setGraph] = useState<{ nodes: CallNode[]; edges: CallEdge[] }>({ nodes: [], edges: [] });
  const [enabledTypes, setEnabledTypes] = useState<Set<string>>(new Set(Object.keys(EDGE_COLORS)));
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

  const loadGraph = useCallback(async () => {
    if (!focusedEntity?.id) {
      setGraph({ nodes: [], edges: [] });
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const projectParam = projectId ? `&project_id=${projectId}` : '';
      const response = await fetch(`${API_URL}/callgraph/focus?entity_id=${focusedEntity.id}&hops=${hops}${projectParam}`, { credentials: 'include' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const nodes: CallNode[] = (data.nodes || []).map((node: any) => ({
        id: `entity:${node.id}`,
        entityId: node.id,
        name: node.name,
        type: node.type,
        file_path: node.file_path,
        start_line: node.start_line,
        source_id: node.source_id,
      }));
      const known = new Set(nodes.map(node => node.id));
      const edges: CallEdge[] = (data.edges || []).map((edge: any) => {
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
        };
      });
      setGraph({ nodes, edges });
      setTruncated(Boolean(data.truncated));
      setTimeout(() => graphRef.current?.zoomToFit(350, 50), 100);
    } catch (err: any) {
      setError(err?.message || t('callGraphView.loadError'));
    } finally {
      setLoading(false);
    }
    // focusedEntity is typed `any`, so the compiler can't narrow the
    // dependency to `.id` on its own — depend on the whole reference to
    // match what it infers.
  }, [focusedEntity, hops, projectId, t]);

  useEffect(() => {
    // queueMicrotask: loadGraph() sets loading/error state before its
    // first await, which reads as a synchronous setState-in-effect to the
    // compiler's analysis if called directly from the effect body.
    queueMicrotask(() => { loadGraph(); });
  }, [loadGraph]);

  const filtered = useMemo(() => {
    const links = graph.edges.filter(edge => enabledTypes.has(edge.type));
    const usedIds = new Set<string>([`entity:${focusedEntity?.id}`]);
    links.forEach(edge => {
      usedIds.add(typeof edge.source === 'string' ? edge.source : edge.source.id);
      usedIds.add(typeof edge.target === 'string' ? edge.target : edge.target.id);
    });
    return { nodes: graph.nodes.filter(node => usedIds.has(node.id)), links };
  }, [graph, enabledTypes, focusedEntity?.id]);

  const exportGraph = async (format: 'json' | 'csv' | 'graphml') => {
    if (!focusedEntity?.id) return;
    const projectParam = projectId ? `&project_id=${projectId}` : '';
    const response = await fetch(`${API_URL}/callgraph/export?entity_id=${focusedEntity.id}&hops=${hops}&format=${format}${projectParam}`, { credentials: 'include' });
    if (!response.ok) return setError(t('callGraphView.exportError', { status: response.status }));
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `callgraph-${focusedEntity.name || focusedEntity.id}.${format === 'graphml' ? 'graphml' : format}`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (!focusedEntity?.id) {
    return <div className="h-full flex flex-col items-center justify-center gap-2 text-ds-zinc-500"><FileCode className="w-10 h-10 opacity-30" /><p className="text-sm">{t('callGraphView.focusFirst')}</p></div>;
  }

  return (
    <div className={cn('h-full flex flex-col', isDark ? 'bg-ds-zinc-950 text-ds-zinc-200' : 'bg-ds-white text-ds-zinc-800')}>
      <div className={cn('px-3 py-2 border-b flex flex-wrap items-center gap-2', isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200')}>
        <div className="min-w-0 mr-auto"><div className="text-xs font-bold truncate">{focusedEntity.name}</div><div className="text-[9px] uppercase tracking-wider text-ds-zinc-500">Call-Graph · {hops} {hops !== 1 ? t('callGraphView.hopUnitPlural') : t('callGraphView.hopUnit')}</div></div>
        {[1, 2, 3].map(value => <button key={value} onClick={() => setHops(value)} className={cn('h-7 px-2 rounded border text-[10px] font-bold', hops === value ? 'border-ds-indigo-500 bg-ds-indigo-500/15 text-ds-indigo-400' : 'border-ds-zinc-700 text-ds-zinc-500')}>{value} {t('callGraphView.hopUnit')}</button>)}
        <button onClick={loadGraph} title={t('callGraphView.reloadTitle')} className="p-1.5 text-ds-zinc-500 hover:text-ds-indigo-400"><RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} /></button>
        <button onClick={() => graphRef.current?.zoom(graphRef.current.zoom() * 1.3, 250)} title={t('callGraphView.zoomInTitle')} className="p-1.5 text-ds-zinc-500 hover:text-ds-indigo-400"><ZoomIn className="w-3.5 h-3.5" /></button>
        <button onClick={() => graphRef.current?.zoom(graphRef.current.zoom() / 1.3, 250)} title={t('callGraphView.zoomOutTitle')} className="p-1.5 text-ds-zinc-500 hover:text-ds-indigo-400"><ZoomOut className="w-3.5 h-3.5" /></button>
        <button onClick={() => graphRef.current?.zoomToFit(350, 50)} title={t('callGraphView.fitAllTitle')} className="p-1.5 text-ds-zinc-500 hover:text-ds-indigo-400"><Maximize2 className="w-3.5 h-3.5" /></button>
      </div>
      <div className={cn('px-3 py-1.5 border-b flex flex-wrap items-center gap-2', isDark ? 'border-ds-zinc-900' : 'border-ds-zinc-100')}>
        {Object.entries(EDGE_COLORS).map(([type, color]) => <button key={type} onClick={() => setEnabledTypes(previous => { const next = new Set(previous); next.has(type) ? next.delete(type) : next.add(type); return next; })} className={cn('px-2 py-1 rounded border text-[9px] font-bold', enabledTypes.has(type) ? 'opacity-100' : 'opacity-35')} style={{ borderColor: color, color }}>{type}</button>)}
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
          nodeLabel={(node: any) => `${node.name} (${node.type})`}
          nodeColor={(node: any) => resolveDsColor(node.unresolved ? 'rgb(var(--ds-warning-base))' : node.entityId === focusedEntity.id ? 'rgb(var(--ds-accent))' : 'rgb(var(--ds-info-base))')}
          nodeVal={(node: any) => node.entityId === focusedEntity.id ? 7 : 4}
          linkColor={(edge: any) => resolveDsColor(edge.resolution === 'resolved' ? EDGE_COLORS[edge.type] : 'rgb(var(--ds-warning-base))')}
          linkWidth={1.5}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          linkLineDash={(edge: any) => edge.resolution === 'resolved' ? null : [4, 3]}
          linkLabel={(edge: any) => `${edge.type} · ${edge.resolution}`}
          onNodeClick={(node: any) => { if (!node.unresolved && node.file_path) onFileSelect(node.file_path, node.start_line, node.source_id); }}
        />}
      </div>
    </div>
  );
}
