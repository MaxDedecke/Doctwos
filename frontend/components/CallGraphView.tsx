"use client";
import type { CodeEntity } from '@/types/domain';
import type { WorkspaceDocument } from '@/types/domain';
import type { ForceGraphMethods, ForceGraphProps } from 'react-force-graph-2d';
import type { CallFlowData, CallFlowEdge } from '@/lib/callFlow';

import { api, API_URL } from '@/app/services/api';
import { ANALYSIS_STATUS_COLOR_TOKEN, formatAnalysisStatusTooltip, type AnalysisStatus } from '@/lib/analysisStatus';
import { resolveDsColor } from '@/lib/designTokens';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { ChangePackageAction } from './ChangePackageAction';
import { AlertTriangle, Compass, FileCode, Loader2, Maximize2, RefreshCw, X, ZoomIn, ZoomOut } from 'lucide-react';
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
  language?: string;
  condition?: string | null;
  decision?: boolean;
  unresolved?: boolean;
  // O-120: nur gesetzt, wenn die Datei dieses Knotens nicht uneingeschränkt
  // analysiert ist (siehe backend/core/analysis_status.py). Bewusst nur auf
  // Datei-Ebene -- welche Entities/Kanten genau unsicher sind, ist O-150s
  // Herkunfts-/Unsicherheitsvertrag, nicht Teil dieses Punkts.
  analysis_status?: AnalysisStatus;
  analysis_reasons?: string[];
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number;
  fy?: number;
};

export type CallEdge = {
  id: string;
  source: string | CallNode;
  target: string | CallNode;
  type: string;
  resolution: string;
  certainty?: 'certain' | 'possible' | 'unresolved';
  originalTypes?: string[];
  start_line?: number | null;
  file_path?: string;
  source_id?: number | string | null;
  originKind?: string;
  sequence?: number | null;
  condition?: string | null;
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
  onInvestigateFromHere?: (entity: Pick<CodeEntity, 'id' | 'name'>) => void;
  onOpenDoc?: (filePath: string, sourceId: number | string | null, locator?: Partial<WorkspaceDocument>) => void;
}

const PROCESS_COLORS: Record<string, string> = {
  entry: '#0ea5e9', step: '#3b82f6', call: '#8b5cf6', branch: '#f59e0b',
  jump: '#f97316', iteration: '#14b8a6', data_access: '#06b6d4',
  external_call: '#ef4444', exit: '#64748b',
};

function traceProcessNodeShape(ctx: CanvasRenderingContext2D, node: CallNode, radius: number) {
  const x = node.x ?? 0;
  const y = node.y ?? 0;
  ctx.beginPath();
  if (node.type === 'branch') {
    ctx.moveTo(x, y - radius);
    ctx.lineTo(x + radius, y);
    ctx.lineTo(x, y + radius);
    ctx.lineTo(x - radius, y);
    ctx.closePath();
  } else if (node.type === 'data_access') {
    ctx.rect(x - radius * 0.78, y - radius * 0.78, radius * 1.56, radius * 1.56);
  } else if (node.type === 'external_call') {
    for (let side = 0; side < 6; side += 1) {
      const angle = Math.PI / 3 * side - Math.PI / 6;
      const px = x + radius * Math.cos(angle);
      const py = y + radius * Math.sin(angle);
      if (side === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
  } else {
    ctx.arc(x, y, radius, 0, 2 * Math.PI);
  }
}

export function ProcessView({ theme, focusedEntity, onFileSelect, projectId, customFlow, onClearCustomFlow, onInvestigateFromHere, onOpenDoc }: Props) {
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const isImpactMode = customFlow?.mode === 'impact';

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

  const [rootOverride, setRootOverride] = useState<Pick<CodeEntity, 'id' | 'name'> | null>(null);
  const lastFocusedEntityIdRef = useRef<number | null>(focusedEntity?.id ?? null);

  useEffect(() => {
    if (focusedEntity?.id !== lastFocusedEntityIdRef.current) {
      lastFocusedEntityIdRef.current = focusedEntity?.id ?? null;
      setRootOverride(null);
    }
  }, [focusedEntity?.id]);

  const customFlowRoot = customFlow?.root;
  const currentRoot = useMemo(() => {
    if (customFlowRoot) {
      return { id: customFlowRoot.id, name: customFlowRoot.name };
    }
    return rootOverride ?? focusedEntity;
  }, [customFlowRoot, rootOverride, focusedEntity]);
  const highlightedEntityId = customFlow?.focus_entity_id ?? currentRoot?.id;

  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return graph.nodes.find(n => n.id === selectedNodeId) ?? null;
  }, [graph.nodes, selectedNodeId]);

  const selectedEdge = useMemo(() => {
    if (!selectedEdgeId) return null;
    return graph.edges.find(edge => edge.id === selectedEdgeId) ?? null;
  }, [graph.edges, selectedEdgeId]);

  const selectedEdgeSource = useMemo(() => {
    if (!selectedEdge) return null;
    if (typeof selectedEdge.source !== 'string') return selectedEdge.source;
    return graph.nodes.find(node => node.id === selectedEdge.source) ?? null;
  }, [graph.nodes, selectedEdge]);

  const selectedEdgeTarget = useMemo(() => {
    if (!selectedEdge) return null;
    if (typeof selectedEdge.target !== 'string') return selectedEdge.target;
    return graph.nodes.find(node => node.id === selectedEdge.target) ?? null;
  }, [graph.nodes, selectedEdge]);

  const rootNodeId = currentRoot?.id != null ? `entity:${currentRoot.id}` : null;
  const changeTargetNode = selectedNode?.entityId != null
    ? selectedNode
    : graph.nodes.find(node => node.entityId === currentRoot?.id) ?? null;
  const canInvestigateFromHere = Boolean(
    !customFlow &&
    !isImpactMode &&
    selectedNode &&
    selectedNode.entityId != null &&
    selectedNode.id !== rootNodeId
  );

  const handleInvestigateFromHere = useCallback(() => {
    if (!selectedNode?.entityId) return;
    const nextRoot = { id: selectedNode.entityId, name: selectedNode.name };
    setRootOverride(nextRoot);
    setSelectedNodeId(`entity:${nextRoot.id}`);
    onInvestigateFromHere?.(nextRoot);
  }, [selectedNode, onInvestigateFromHere]);

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
      setSelectedEdgeId(null);
      const types = Array.from(new Set(edges.map(edge => edge.type))).sort();
      setAvailableTypes(types);
      setEnabledTypes(new Set(types));
      setTruncated(Boolean(customFlow.truncated));
      setSelectedNodeId(`entity:${customFlow.focus_entity_id ?? customFlow.root.id}`);
      setTimeout(() => graphRef.current?.zoomToFit(350, 50), 100);
    });
  }, [customFlow]);

  const loadGraph = useCallback(async () => {
    if (customFlow) return;
    if (!currentRoot?.id) {
      setGraph({ nodes: [], edges: [] });
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const projectParam = projectId ? `&project_id=${projectId}` : '';
      const response = await api.fetch(`${API_URL}/process/focus?entity_id=${currentRoot.id}&hops=${hops}${projectParam}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      type ProcessNode = {
        id: string; kind: string; label: string; entity_id?: number | null;
        locator: { file_path: string; start_line: number; source_id?: number | null };
        language: string; condition?: string | null;
      };
      type ProcessTransition = {
        id: string; source: string; target: string; kind: string; resolution: string;
        certainty: 'certain' | 'possible' | 'unresolved'; code_edge_types: string[];
        origin_kind: string; sequence?: number | null; condition?: string | null;
        locator: { file_path: string; start_line: number; source_id?: number | null };
        meta?: CallFlowEdge['meta'];
      };
      const data: { nodes: ProcessNode[]; transitions: ProcessTransition[]; truncation: { truncated: boolean; reasons: string[] } } = await response.json();
      const decisionSourceIds = new Set((data.transitions || [])
        .filter(transition => transition.kind === 'branch')
        .map(transition => transition.source));

      setGraph(prevGraph => {
        const existingPositions = new Map<string, { x?: number; y?: number; vx?: number; vy?: number; fx?: number; fy?: number }>();
        prevGraph.nodes.forEach(n => {
          if (n.x != null && n.y != null) {
            existingPositions.set(n.id, { x: n.x, y: n.y, vx: n.vx, vy: n.vy, fx: n.fx, fy: n.fy });
          }
        });

        const nodes: CallNode[] = (data.nodes || []).map((node) => {
          const pos = existingPositions.get(node.id);
          return {
            id: node.id,
            entityId: node.entity_id ?? undefined,
            name: node.label,
            type: node.kind,
            file_path: node.locator.file_path,
            start_line: node.locator.start_line,
            source_id: node.locator.source_id,
            language: node.language,
            condition: node.condition,
            decision: decisionSourceIds.has(node.id),
            unresolved: node.kind === 'external_call',
            ...(pos ? { x: pos.x, y: pos.y, vx: pos.vx, vy: pos.vy, fx: pos.fx, fy: pos.fy } : {}),
          };
        });

        const edges: CallEdge[] = (data.transitions || []).map((edge) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          type: edge.kind,
          resolution: edge.resolution,
          certainty: edge.certainty,
          originalTypes: edge.code_edge_types,
          start_line: edge.locator.start_line,
          file_path: edge.locator.file_path,
          source_id: edge.locator.source_id,
          originKind: edge.origin_kind,
          sequence: edge.sequence,
          condition: edge.condition,
          meta: edge.meta,
        }));

        if (existingPositions.size === 0) {
          setTimeout(() => graphRef.current?.zoomToFit(350, 50), 100);
        }

        return { nodes, edges };
      });

      const types = Array.from(new Set((data.transitions || []).map(edge => edge.kind))).sort();
      setAvailableTypes(types);
      setEnabledTypes(new Set(types));
      setTruncated(Boolean(data.truncation?.truncated));
      setSelectedEdgeId(null);
      setSelectedNodeId(`entity:${currentRoot.id}`);
    } catch (err) {
      setError((err instanceof Error ? err.message : undefined) || t('callGraphView.loadError'));
    } finally {
      setLoading(false);
    }
  }, [customFlow, currentRoot, hops, projectId, t]);

  useEffect(() => {
    // queueMicrotask: loadGraph() sets loading/error state before its
    // first await, which reads as a synchronous setState-in-effect to the
    // compiler's analysis if called directly from the effect body.
    queueMicrotask(() => { loadGraph(); });
  }, [loadGraph]);

  const filtered = useMemo(() => {
    const links = graph.edges.filter(edge => enabledTypes.has(edge.type));
    const usedIds = new Set<string>([`entity:${currentRoot?.id}`]);
    links.forEach(edge => {
      usedIds.add(typeof edge.source === 'string' ? edge.source : edge.source.id);
      usedIds.add(typeof edge.target === 'string' ? edge.target : edge.target.id);
    });
    return { nodes: graph.nodes.filter(node => usedIds.has(node.id)), links };
  }, [graph, enabledTypes, currentRoot?.id]);

  const highlightedEdgeId = customFlow?.highlighted_edge_id;
  const animatedOriginId = selectedNodeId ?? (
    highlightedEntityId != null ? `entity:${highlightedEntityId}` : null
  );

  const isEdgeHighlighted = useCallback((edge: CallEdge) => {
    if (highlightedEdgeId == null) return false;
    return edge.id === `edge:${highlightedEdgeId}` || edge.id === String(highlightedEdgeId);
  }, [highlightedEdgeId]);

  const isEdgeOutgoingFromSelection = useCallback((edge: CallEdge) => {
    if (!animatedOriginId) return false;
    const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
    return sourceId === animatedOriginId;
  }, [animatedOriginId]);

  const activeEdge = useMemo(() => {
    if (highlightedEdgeId == null) return null;
    return filtered.links.find(isEdgeHighlighted) ?? null;
  }, [filtered.links, isEdgeHighlighted, highlightedEdgeId]);

  const activeSourceId = useMemo(() => {
    if (!activeEdge) return null;
    return typeof activeEdge.source === 'object' ? activeEdge.source.id : activeEdge.source;
  }, [activeEdge]);

  const activeTargetId = useMemo(() => {
    if (!activeEdge) return null;
    return typeof activeEdge.target === 'object' ? activeEdge.target.id : activeEdge.target;
  }, [activeEdge]);

  const isNodePrimary = useCallback((node: CallNode) => {
    if (activeTargetId != null && (node.id === activeTargetId || `entity:${node.entityId}` === activeTargetId)) {
      return true;
    }
    if (selectedNodeId != null) {
      return node.id === selectedNodeId;
    }
    if (highlightedEntityId != null) {
      return node.entityId === highlightedEntityId || node.id === `entity:${highlightedEntityId}` || String(node.entityId) === String(highlightedEntityId);
    }
    return false;
  }, [activeTargetId, highlightedEntityId, selectedNodeId]);

  const isNodeSource = useCallback((node: CallNode) => {
    if (!activeSourceId) return false;
    return node.id === activeSourceId || `entity:${node.entityId}` === activeSourceId;
  }, [activeSourceId]);

  if (!currentRoot?.id) {
    return <div className="h-full flex flex-col items-center justify-center gap-2 text-ds-zinc-500"><FileCode className="w-10 h-10 opacity-30" /><p className="text-sm">{t('callGraphView.focusFirst')}</p></div>;
  }

  return (
    <div className={cn('h-full flex flex-col', isDark ? 'bg-ds-zinc-950 text-ds-zinc-200' : 'bg-ds-white text-ds-zinc-800')}>
      <div className={cn('px-3 py-2 border-b flex flex-wrap items-center gap-2', isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200')}>
        <div className="min-w-0 mr-auto">
          <div className="text-xs font-bold truncate flex items-center gap-1.5">
            <span>{currentRoot.name}</span>
            {customFlow && (
              <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-ds-indigo-500/15 text-ds-indigo-400 border border-ds-indigo-500/30">
                {isImpactMode ? t('callGraphView.impactTitle') : t('callGraphView.flowTitle')}
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
                {t('callGraphView.processTitle')} · {hops} {hops !== 1 ? t('callGraphView.hopUnitPlural') : t('callGraphView.hopUnit')}
              </>
            )}
          </div>
        </div>
        {canInvestigateFromHere && (
          <button
            type="button"
            onClick={handleInvestigateFromHere}
            data-testid="investigate-from-here"
            className="h-7 px-2.5 rounded border border-ds-indigo-500 bg-ds-indigo-500/15 text-ds-indigo-400 hover:bg-ds-indigo-500/25 text-[10px] font-bold flex items-center gap-1.5 transition-colors cursor-pointer"
            title={t('callGraphView.investigateFromHereTitle')}
          >
            <Compass className="w-3.5 h-3.5" />
            <span>{t('callGraphView.investigateFromHere')}</span>
          </button>
        )}
        <ChangePackageAction
          projectId={projectId}
          target={changeTargetNode?.entityId != null ? {
            entityId: changeTargetNode.entityId,
            sourceId: changeTargetNode.source_id,
            label: changeTargetNode.name,
          } : currentRoot ? { entityId: currentRoot.id, label: currentRoot.name } : null}
          theme={theme}
          onOpenCode={onFileSelect}
          onOpenDoc={onOpenDoc}
        />
        {customFlow && onClearCustomFlow && (
          <button
            type="button"
            onClick={() => {
              setRootOverride(null);
              setSelectedNodeId(null);
              onClearCustomFlow();
            }}
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
        {availableTypes.map(type => {
          const color = PROCESS_COLORS[type] ?? '#64748b';
          return <button key={type} onClick={() => setEnabledTypes(previous => { const next = new Set(previous); next.has(type) ? next.delete(type) : next.add(type); return next; })} className={cn('px-2 py-1 rounded border text-[9px] font-bold', enabledTypes.has(type) ? 'opacity-100' : 'opacity-35')} style={{ borderColor: color, color }}>{t(`callGraphView.processKinds.${type}`)}</button>;
        })}
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
          nodeColor={(node: CallNode) => {
            if (node.unresolved) return resolveDsColor('rgb(var(--ds-warning-base))');
            if (isNodePrimary(node)) return isDark ? '#0284c7' : '#0284c7';
            if (isNodeSource(node)) return isDark ? '#047857' : '#059669';
            return PROCESS_COLORS[node.type] ?? resolveDsColor('rgb(var(--ds-info-base))');
          }}
          nodeVal={(node: CallNode) => isNodePrimary(node) ? 8 : (isNodeSource(node) ? 6 : 4)}
          nodeCanvasObjectMode={() => 'replace'}
          nodeCanvasObject={(node: CallNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const isPrimary = isNodePrimary(node);
            const isSource = isNodeSource(node) && !isPrimary;
            const hasActiveContext = Boolean(highlightedEdgeId != null || (customFlow && customFlow.focus_entity_id != null));
            const isDimmed = hasActiveContext && !isPrimary && !isSource;

            ctx.save();
            if (isDimmed) {
              ctx.globalAlpha = isDark ? 0.28 : 0.35;
            }

            const radius = isPrimary ? 9 : (isSource ? 8.5 : 7);
            const now = performance.now();

            // Circling white animation and pulse on current standpoint node ("wo bin ich")
            if (isPrimary) {
              // 1. Radar ripple wave expanding outward
              const pulseProgress = (now % 1200) / 1200;
              const pulseR = radius + (pulseProgress * 12) / globalScale;
              const pulseAlpha = (1 - pulseProgress) * (isDark ? 0.75 : 0.55);
              ctx.beginPath();
              ctx.arc(node.x ?? 0, node.y ?? 0, pulseR, 0, 2 * Math.PI);
              ctx.strokeStyle = isDark
                ? `rgba(56, 189, 248, ${pulseAlpha})`
                : `rgba(2, 132, 199, ${pulseAlpha})`;
              ctx.lineWidth = 2 / globalScale;
              ctx.stroke();

              // 2. High-contrast guide track (provides contrast on white canvas!)
              const trackR = radius + 3 / globalScale;
              ctx.beginPath();
              ctx.arc(node.x ?? 0, node.y ?? 0, trackR, 0, 2 * Math.PI);
              ctx.strokeStyle = isDark ? 'rgba(255, 255, 255, 0.25)' : 'rgba(15, 23, 42, 0.35)';
              ctx.lineWidth = 2.5 / globalScale;
              ctx.stroke();

              // 3. Circling white animation (rotating arc)
              const spinAngle = (now / 360) % (2 * Math.PI);
              const arcLength = Math.PI * 0.75;
              ctx.save();
              ctx.beginPath();
              ctx.arc(node.x ?? 0, node.y ?? 0, trackR, spinAngle, spinAngle + arcLength);
              ctx.lineWidth = 3.5 / globalScale;
              ctx.lineCap = 'round';
              if (!isDark) {
                ctx.shadowColor = 'rgba(0, 0, 0, 0.7)';
                ctx.shadowBlur = 4;
              } else {
                ctx.shadowColor = 'rgba(255, 255, 255, 0.95)';
                ctx.shadowBlur = 8;
              }
              ctx.strokeStyle = '#ffffff';
              ctx.stroke();

              // 4. White comet head orb
              const headAngle = spinAngle + arcLength;
              const headX = (node.x ?? 0) + trackR * Math.cos(headAngle);
              const headY = (node.y ?? 0) + trackR * Math.sin(headAngle);
              ctx.beginPath();
              ctx.arc(headX, headY, 2.5 / globalScale, 0, 2 * Math.PI);
              ctx.fillStyle = '#ffffff';
              if (!isDark) {
                ctx.shadowColor = 'rgba(0, 0, 0, 0.8)';
                ctx.shadowBlur = 3;
              } else {
                ctx.shadowColor = '#38bdf8';
                ctx.shadowBlur = 6;
              }
              ctx.fill();
              ctx.restore();
            } else if (isSource) {
              // Origin / Source indicator ("von wo"): steady/pulsing green halo
              const sourceR = radius + 2.5 / globalScale;
              ctx.beginPath();
              ctx.arc(node.x ?? 0, node.y ?? 0, sourceR, 0, 2 * Math.PI);
              ctx.strokeStyle = isDark ? '#10b981' : '#059669';
              ctx.lineWidth = 2.5 / globalScale;
              ctx.stroke();
            }

            // Node circle fill
            traceProcessNodeShape(ctx, node, radius);
            if (node.unresolved) {
              ctx.fillStyle = resolveDsColor('rgb(var(--ds-warning-base))');
            } else if (isPrimary) {
              ctx.fillStyle = isDark ? '#0284c7' : '#0284c7';
            } else if (isSource) {
              ctx.fillStyle = isDark ? '#047857' : '#059669';
            } else {
              ctx.fillStyle = PROCESS_COLORS[node.type] ?? resolveDsColor('rgb(var(--ds-info-base))');
            }
            ctx.fill();
            ctx.save();
            ctx.lineWidth = 1.25 / globalScale;
            ctx.strokeStyle = isPrimary ? (isDark ? '#38bdf8' : '#ffffff') : (isDark ? 'rgba(255,255,255,0.75)' : 'rgba(15,23,42,0.6)');
            if (node.type === 'external_call') ctx.setLineDash([2 / globalScale, 1.5 / globalScale]);
            ctx.stroke();
            ctx.restore();

            // Inner border for primary node
            if (isPrimary) {
              traceProcessNodeShape(ctx, node, radius);
              ctx.strokeStyle = isDark ? '#38bdf8' : '#ffffff';
              ctx.lineWidth = 2 / globalScale;
              ctx.stroke();
            }

            // The entry is marked with a second ring in addition to its color.
            if (node.type === 'entry') {
              ctx.beginPath();
              ctx.arc(node.x ?? 0, node.y ?? 0, radius * 0.58, 0, 2 * Math.PI);
              ctx.strokeStyle = isDark ? '#e0f2fe' : '#075985';
              ctx.lineWidth = 1.25 / globalScale;
              ctx.stroke();
            }

            if (node.decision) {
              const badgeRadius = 3.5 / globalScale;
              const badgeX = (node.x ?? 0) + radius * 0.78;
              const badgeY = (node.y ?? 0) - radius * 0.78;
              ctx.beginPath();
              ctx.moveTo(badgeX, badgeY - badgeRadius);
              ctx.lineTo(badgeX + badgeRadius, badgeY);
              ctx.lineTo(badgeX, badgeY + badgeRadius);
              ctx.lineTo(badgeX - badgeRadius, badgeY);
              ctx.closePath();
              ctx.fillStyle = PROCESS_COLORS.branch;
              ctx.fill();
              ctx.strokeStyle = isDark ? '#fff7ed' : '#7c2d12';
              ctx.lineWidth = 1 / globalScale;
              ctx.stroke();
            }

            // O-120: analysis status dash ring
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

            if (globalScale > 0.45) {
              const label = node.name ?? '';
              const maxLen = Math.min(18, Math.max(7, Math.floor(globalScale * 8)));
              const truncated = label.length > maxLen ? `${label.slice(0, maxLen)}…` : label;
              ctx.font = `${isPrimary ? 'bold ' : ''}${Math.min(11, 8 / globalScale * 1.8)}px Inter, system-ui, sans-serif`;
              ctx.textAlign = 'center';
              ctx.textBaseline = 'top';
              ctx.fillStyle = isPrimary
                ? (isDark ? '#f8fafc' : '#0f172a')
                : resolveDsColor(isDark ? 'rgb(var(--ds-neutral-200))' : 'rgb(var(--ds-neutral-600))');
              ctx.fillText(truncated, node.x ?? 0, (node.y ?? 0) + radius + 3 / globalScale);
            }

            ctx.restore();
          }}
          linkColor={(edge: CallEdge) => {
            const isHighlighted = isEdgeHighlighted(edge);
            if (isHighlighted) {
              return isDark ? '#38bdf8' : '#0284c7';
            }
            if (highlightedEdgeId != null) {
              return isDark ? 'rgba(148, 163, 184, 0.15)' : 'rgba(100, 116, 139, 0.25)';
            }
            if (edge.certainty === 'unresolved') return resolveDsColor('rgb(var(--ds-error-base))');
            if (edge.certainty === 'possible') return resolveDsColor('rgb(var(--ds-warning-base))');
            return PROCESS_COLORS[edge.type] ?? resolveDsColor('rgb(var(--ds-info-base))');
          }}
          linkWidth={(edge: CallEdge) => isEdgeHighlighted(edge) ? 4.5 : 1.5}
          linkDirectionalArrowLength={(edge: CallEdge) => isEdgeHighlighted(edge) ? 6.5 : 4}
          linkDirectionalArrowRelPos={1}
          linkLineDash={(edge: CallEdge) => edge.certainty === 'certain' ? null : [4, 3]}
          linkDirectionalParticles={(edge: CallEdge) => isEdgeHighlighted(edge) ? 5 : (isEdgeOutgoingFromSelection(edge) ? 2 : 0)}
          linkDirectionalParticleSpeed={(edge: CallEdge) => isEdgeHighlighted(edge) ? 0.012 : 0.004}
          linkDirectionalParticleWidth={(edge: CallEdge) => isEdgeHighlighted(edge) ? 5 : 2.5}
          linkDirectionalParticleCanvasObject={(x: number, y: number, edge: CallEdge, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const isHighlighted = isEdgeHighlighted(edge);
            const r = (isHighlighted ? 3.5 : 2) / globalScale;
            ctx.save();
            ctx.beginPath();
            ctx.arc(x, y, r, 0, 2 * Math.PI);
            if (!isDark) {
              ctx.fillStyle = '#ffffff';
              ctx.shadowColor = 'rgba(0, 0, 0, 0.65)';
              ctx.shadowBlur = 3;
              ctx.fill();
              ctx.lineWidth = 1.2 / globalScale;
              ctx.strokeStyle = isHighlighted ? '#0284c7' : '#64748b';
              ctx.stroke();
            } else {
              ctx.fillStyle = '#ffffff';
              ctx.shadowColor = isHighlighted ? '#38bdf8' : '#94a3b8';
              ctx.shadowBlur = isHighlighted ? 8 : 4;
              ctx.fill();
            }
            ctx.restore();
          }}
          autoPauseRedraw={false}
          linkLabel={(edge: CallEdge) => `${edge.type} · ${edge.certainty ?? edge.resolution}${edge.originalTypes?.length ? ` · ${edge.originalTypes.join(', ')}` : ''}${edge.meta?.resolution_reason ? ` · ${edge.meta.resolution_reason}` : ''}`}
          onLinkClick={(edge: CallEdge) => {
            if (isImpactMode) return;
            setSelectedEdgeId(edge.id);
            const source = typeof edge.source === 'string'
              ? graph.nodes.find(node => node.id === edge.source) : edge.source;
            const path = edge.file_path || source?.file_path;
            if (path) onFileSelect(path, edge.start_line ?? source?.start_line, edge.source_id ?? source?.source_id);
          }}
          onNodeClick={(node: CallNode) => {
            if (isImpactMode) return;
            setSelectedEdgeId(null);
            setSelectedNodeId(node.id);
            if (!node.unresolved && node.file_path) onFileSelect(node.file_path, node.start_line, node.source_id);
          }}
        />}
      </div>
      {selectedEdge && !isImpactMode && (
        <section
          aria-label={t('callGraphView.transitionDetails.title')}
          data-testid="process-transition-details"
          className={cn(
            'max-h-[34%] min-h-[112px] shrink-0 overflow-y-auto border-t px-3 py-2.5',
            isDark ? 'border-ds-zinc-800 bg-ds-zinc-900/80' : 'border-ds-zinc-200 bg-ds-zinc-50',
          )}
        >
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] font-semibold">
                <span>{selectedEdgeSource?.name ?? (typeof selectedEdge.source === 'string' ? selectedEdge.source : selectedEdge.source.name)}</span>
                <span className="text-ds-zinc-500" aria-hidden="true">→</span>
                <span>{selectedEdgeTarget?.name ?? (typeof selectedEdge.target === 'string' ? selectedEdge.target : selectedEdge.target.name)}</span>
                <span className="rounded border px-1.5 py-0.5 text-[9px]" style={{ borderColor: PROCESS_COLORS[selectedEdge.type] ?? '#64748b', color: PROCESS_COLORS[selectedEdge.type] ?? '#64748b' }}>
                  {t(`callGraphView.processKinds.${selectedEdge.type}`)}
                </span>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[10px] sm:grid-cols-3">
                <div>
                  <span className="text-ds-zinc-500">{t('callGraphView.transitionDetails.certainty')}: </span>
                  <span>{selectedEdge.certainty ? t(`callGraphView.certainty.${selectedEdge.certainty}`) : t('callGraphView.transitionDetails.notProvided')}</span>
                </div>
                <div>
                  <span className="text-ds-zinc-500">{t('callGraphView.transitionDetails.resolution')}: </span>
                  <span>{t(`callGraphView.resolution.${selectedEdge.resolution}`)}</span>
                </div>
                {selectedEdge.originKind && (
                  <div>
                    <span className="text-ds-zinc-500">{t('callGraphView.transitionDetails.origin')}: </span>
                    <span>{t(`callGraphView.transitionDetails.origins.${selectedEdge.originKind}`)}</span>
                  </div>
                )}
                <div>
                  <span className="text-ds-zinc-500">{t('callGraphView.transitionDetails.originalTypes')}: </span>
                  <span className="font-mono">{selectedEdge.originalTypes?.length ? selectedEdge.originalTypes.join(', ') : t('callGraphView.transitionDetails.noOriginalType')}</span>
                </div>
                {selectedEdge.sequence != null && (
                  <div>
                    <span className="text-ds-zinc-500">{t('callGraphView.transitionDetails.sequence')}: </span>
                    <span>{selectedEdge.sequence}</span>
                  </div>
                )}
                {selectedEdge.condition && (
                  <div className="col-span-2 sm:col-span-3">
                    <span className="text-ds-zinc-500">{t('callGraphView.transitionDetails.condition')}: </span>
                    <span className="break-words">{selectedEdge.condition}</span>
                  </div>
                )}
                {selectedEdge.meta?.resolution_reason && (
                  <div className="col-span-2 sm:col-span-3">
                    <span className="text-ds-zinc-500">{t('callGraphView.transitionDetails.reason')}: </span>
                    <span className="break-words">{selectedEdge.meta.resolution_reason}</span>
                  </div>
                )}
                <div className="col-span-2 sm:col-span-3 font-mono text-ds-zinc-500">
                  {selectedEdge.file_path || selectedEdgeSource?.file_path || t('callGraphView.transitionDetails.sourceUnavailable')}
                  {(selectedEdge.start_line ?? selectedEdgeSource?.start_line) != null && `:${selectedEdge.start_line ?? selectedEdgeSource?.start_line}`}
                </div>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {(selectedEdge.file_path || selectedEdgeSource?.file_path) && (
                <button
                  type="button"
                  onClick={() => {
                    const path = selectedEdge.file_path || selectedEdgeSource?.file_path;
                    if (path) onFileSelect(path, selectedEdge.start_line ?? selectedEdgeSource?.start_line, selectedEdge.source_id ?? selectedEdgeSource?.source_id);
                  }}
                  className="inline-flex h-7 items-center gap-1.5 rounded border border-ds-indigo-500/50 px-2 text-[10px] font-semibold text-ds-indigo-400 hover:bg-ds-indigo-500/10"
                >
                  <FileCode className="h-3 w-3" />
                  {t('callGraphView.transitionDetails.openSource')}
                </button>
              )}
              <button
                type="button"
                onClick={() => setSelectedEdgeId(null)}
                aria-label={t('callGraphView.transitionDetails.close')}
                className="rounded p-1 text-ds-zinc-500 hover:text-ds-zinc-200"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

// Stored workspace panels still use the technical `callgraph` identifier.
export const CallGraphView = ProcessView;
