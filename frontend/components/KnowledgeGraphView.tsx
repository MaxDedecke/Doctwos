"use client";

import { InsightGraphDetails } from './InsightGraphDetails';
import type { AgentGraphViewAction, CodeEntity, WorkspaceDocument } from '@/types/domain';
import type { ForceGraphMethods, ForceGraphProps } from 'react-force-graph-2d';

import type { GraphNode, GraphEdge } from '@/lib/knowledgeGraphTypes';
import { createKnowledgeGraphRenderer, getNodeDisplayLabel, graphEdgeDirection, graphEdgeType, type GraphViewport } from '@/lib/knowledgeGraphRendering';
import { api, API_URL } from '@/app/services/api';
import {
  EDGE_TYPE_COLORS,
  NODE_TYPE_TAXONOMY,
  getEntityTypeLabel,
  EDGE_DIRECTION_TAXONOMY,
  getGraphEdgeColor,
  getGraphEdgeLabelKey,
  getGraphNodeCategory,
  getGraphNodeColor,
  type GraphEdgeDirection,
} from '@/lib/graphTaxonomy';
import { canvasColor, resolveDsColor } from '@/lib/designTokens';
import { useGraphSourceFocus } from '@/hooks/useGraphSourceFocus';
import { filterVisibleGraph } from '@/lib/graphVisibility';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { useKnowledgeGraphLayout } from '@/hooks/useKnowledgeGraphLayout';
import { useGraphExpansion } from '@/hooks/useGraphExpansion';
import { canExpandInPlace, hiddenEdgeCounts, type GraphData } from '@/lib/graphExpansion';
import { useGraphStyleRevision } from '@/hooks/useGraphStyleRevision';
import { createGraphScene } from '@/lib/knowledgeGraphLayout';
import { AlertTriangle, ArrowLeft, BookOpen, Check, Crosshair, ExternalLink, Eye, Info, Link2, Loader2, Maximize2, Minus, MoreHorizontal, Plus, RefreshCw, Search, SlidersHorizontal, Workflow, X, ZoomIn, ZoomOut } from 'lucide-react';
import { createPortal } from 'react-dom';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GraphSourceFocus } from './GraphSourceFocus';
import { GraphFilterPanel } from './GraphFilterPanel';
import { GraphToolPanel } from './GraphToolPanel';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from './ui/dropdown-menu';
import { KnowledgeNodeIcon } from './KnowledgeNodeIcon';

// ForceGraph2D will be loaded dynamically on mount

/* ── Shared taxonomy (kept exported for existing view consumers/tests) ─────── */

export const UNIFIED_NODE_TYPES = NODE_TYPE_TAXONOMY;

export function getNodeType(node: GraphNode): string {
  return getGraphNodeCategory(node);
}

export function nodeColor(node: GraphNode): string {
  return getGraphNodeColor(node);
}

function nodeTypeKey(node: GraphNode): string {
  return getNodeType(node);
}

/**
 * Beim Zurückkehren aus einer Nachbarschaft bleibt der Startknoten ("Anker") ausgewählt, damit man
 * ihn in der Übersicht nicht verliert. Fehlt er dort (z. B. weil die Übersicht gekappt wurde), wird er
 * samt seiner Kanten zu Knoten der Übersicht ergänzt.
 */
export function withKeptAnchor(
  nodes: GraphNode[],
  edges: GraphEdge[],
  keep: { node: GraphNode; edges: GraphEdge[] } | null | undefined,
) {
  if (!keep || nodes.some(n => n.id === keep.node.id)) return { nodes, edges };
  const present = new Set([...nodes.map(n => n.id), keep.node.id]);
  const endpoint = (end: GraphEdge['source']) => (typeof end === 'object' ? end.id : end);
  const known = new Set(edges.map(e => e.id));
  const extraEdges = keep.edges.filter(e => !known.has(e.id) && present.has(endpoint(e.source)) && present.has(endpoint(e.target)));
  return { nodes: [...nodes, keep.node], edges: [...edges, ...extraEdges] };
}

export const LINK_COLORS = EDGE_TYPE_COLORS;

export function getLinkLabel(t: (key: string) => string, type: string): string | undefined {
  const key = getGraphEdgeLabelKey(type);
  return key ? t(key) : undefined;
}

/**
 * Callers hand `selectedEntity.id`/`projectEntities[].id` in whatever shape they have on
 * hand: a raw CodeEntity.id number (Monaco decoration clicks, project entity list), an
 * `entity:<id>` graph-node id, or the `ent_<id>` string this component originally expected
 * (never actually produced anywhere — kept for compatibility). Accept all of them.
 */
function extractEntityDbId(id: unknown): number | null {
  if (typeof id === 'number' && Number.isFinite(id)) return id;
  if (typeof id === 'string') {
    const match = /^(?:ent_|entity:)?(\d+)$/.exec(id);
    if (match) return parseInt(match[1], 10);
  }
  return null;
}

/* ── Types ───────────────────────────────────────────────────────────────────── */

export type { GraphNode, GraphEdge } from '@/lib/knowledgeGraphTypes';
export { isEdgeDirected } from '@/lib/knowledgeGraphRendering';

interface Props {
  theme: string;
  selectedProject: { id: number; name: string } | null;
  selectedEntity?: CodeEntity | null;
  selectedFile?: string | null;
  selectedDoc?: WorkspaceDocument | null;
  projectEntities?: CodeEntity[];
  onEntitySelect?: (ent: CodeEntity) => Promise<void> | void;
  // O-091: the ONLY navigation callback for both node kinds. The target view
  // (code/doc/webview) is decided exactly once behind this callback, in
  // usePanelNavigation::handlePanelFileSelect via getSelectionViewType -- this
  // component must not route document nodes on a second, parallel path.
  onFileSelect?: (path: string, line?: number | null, sourceId?: number | string | null, openIfMissing?: boolean) => Promise<void> | void;
  // Kept for callers restoring existing workspace layouts. The graph itself
  // adapts to its measured panel size, independently of the workspace grid.
  layoutMode?: '1-pane' | 'split' | '3-col' | '4-grid';
  agentGraphFocus?: AgentGraphViewAction['target'] | null;
}

// A fresh `[]` literal as a default parameter value is a NEW array reference on
// every render in which the caller omits the prop -- fine as a plain render
// output, but the render-time "adjust state" comparison below (`prevFocusDeps.
// projectEntities !== projectEntities`) relies on referential stability to ever
// become false. With a literal default it never does, so it would fire on every
// single render (an infinite render loop) whenever a caller doesn't pass
// `projectEntities`. Every current caller happens to always pass it, so this was
// latent until testing without every prop first exercised it (O-053 test work).
const EMPTY_PROJECT_ENTITIES: CodeEntity[] = [];

/* ── Component ───────────────────────────────────────────────────────────────── */

export function KnowledgeGraphView({
  theme,
  selectedProject,
  selectedEntity,
  selectedFile,
  selectedDoc,
  projectEntities = EMPTY_PROJECT_ENTITIES,
  onEntitySelect,
  onFileSelect,
  agentGraphFocus
}: Props) {
  const { t, language } = useLanguage();
  const isDark = theme === 'dark';

  const [rawNodes, setRawNodes] = useState<GraphNode[]>([]);
  const [rawEdges, setRawEdges] = useState<GraphEdge[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  // Purely visual "soft focus": connected nodes/edges just render at full opacity
  // while everything else is dimmed, without a separate backend fetch. Used to
  // carry the comment "the overview already carries every link, so a restricted
  // dataset wouldn't add anything" -- true before O-053, no longer: the overview
  // is now capped (KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES) for large projects, so a
  // node's real neighborhood can exceed what a dimmed-down view of the loaded
  // (possibly truncated) overview shows. `loadNeighborhood` below is the actual
  // fix for that case — a real GET /graph/focus fetch, independent of whatever
  // got cut from the overview.
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);

  // O-053: whether the currently loaded overview was capped server-side, and
  // hard-focus state for "load this node's real neighborhood from the DB"
  // (as opposed to the soft focus above, which only dims the already-loaded data).
  const [overviewTruncation, setOverviewTruncation] = useState<{ shown: number; total: number; edgesSampled: boolean } | null>(null);
  const [viewMode, setViewMode] = useState<'overview' | 'neighborhood'>('overview');
  const [neighborhoodError, setNeighborhoodError] = useState<string | null>(null);
  const [isLoadingNeighborhood, setIsLoadingNeighborhood] = useState(false);
  const [neighborhoodFocusNode, setNeighborhoodFocusNode] = useState<GraphNode | null>(null);
  const [neighborhoodCursor, setNeighborhoodCursor] = useState<string | null>(null);
  const [neighborhoodHasMore, setNeighborhoodHasMore] = useState<boolean>(false);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [neighborhoodRelationships, setNeighborhoodRelationships] = useState<Array<'code_dependency' | 'documented' | 'manual'>>(['code_dependency', 'documented', 'manual']);
  const [neighborhoodLimit, setNeighborhoodLimit] = useState(150);
  const [traversalDirection, setTraversalDirection] = useState<'incoming' | 'outgoing' | 'both'>('both');
  const [traversalHops, setTraversalHops] = useState<1 | 2 | 3 | 4 | 5>(1);
  // The knowledge graph is a relationship view. Unlinked inventory belongs in
  // a paginated list, because rendering it here creates thousands of meaningless
  // force-layout nodes and obscures the actual code/document evidence network.
  const onlyLinked = true;

  // Keep the expensive initial overview alive while a node neighborhood is shown.
  // The neighborhood replaces the rendered data temporarily, but must not discard
  // the large overview which the user already waited for.
  const { focusSourceId, resetFocus, changeFocus, addFocusParam } = useGraphSourceFocus();
  const overviewCacheRef = useRef<{
    projectId: number | null;
    includeIsolated: boolean;
    nodes: GraphNode[];
    edges: GraphEdge[];
    truncation: { shown: number; total: number; edgesSampled: boolean } | null;
  } | null>(null);

  // Manual link creation (connect the selected node to any other loaded node)
  const [isLinkPickerOpen, setIsLinkPickerOpen] = useState(false);
  const [linkPickerQuery, setLinkPickerQuery] = useState('');
  const [linkPickerTargetId, setLinkPickerTargetId] = useState<string | null>(null);
  const [linkDescription, setLinkDescription] = useState('');
  const [manualLinkDirection, setManualLinkDirection] = useState<GraphEdgeDirection>('undirected');
  const [isCreatingLink, setIsCreatingLink] = useState(false);
  const [linkCreateError, setLinkCreateError] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [panelSize, setPanelSize] = useState({ width: 0, height: 0 });
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const graphRef = useRef<ForceGraphMethods<GraphNode, GraphEdge> | undefined>(undefined);

  const [ForceGraphComponent, setForceGraphComponent] = useState<React.ComponentType<ForceGraphProps<GraphNode, GraphEdge> & { ref?: React.MutableRefObject<ForceGraphMethods<GraphNode, GraphEdge> | undefined> }> | null>(null);

  useEffect(() => {
    import('react-force-graph-2d').then((mod) => {
      setForceGraphComponent(() => mod.default);
    });
  }, []);

  const [hiddenNodeTypes, setHiddenNodeTypes] = useState<Set<string>>(new Set());
  const [hiddenLinkTypes, setHiddenLinkTypes] = useState<Set<string>>(new Set());
  const [hiddenEdgeDirections, setHiddenEdgeDirections] = useState<Set<GraphEdgeDirection>>(new Set());
  const [linkFilterResetToken, setLinkFilterResetToken] = useState(0);
  const [toolSurface, setToolSurface] = useState<'filters' | 'legend' | null>(null);
  const [focusDetails, setFocusDetails] = useState(false);
  const detailsTriggerRef = useRef<HTMLButtonElement>(null);
  const filterTriggerRef = useRef<HTMLButtonElement>(null);
  const viewTriggerRef = useRef<HTMLButtonElement>(null);
  const menuOpensPanelRef = useRef(false);
  const closeToolSurface = () => {
    const trigger = toolSurface === 'filters' ? filterTriggerRef.current : viewTriggerRef.current;
    setToolSurface(null);
    // Wait until the previous tool and any menu focus scope have unmounted.
    requestAnimationFrame(() => { if (trigger?.isConnected) trigger.focus(); });
  };

  // Moves within the detail panel (node -> one of its edges -> an endpoint) are remembered so the
  // back arrow returns along the same path. Each step records where it led; once the selection
  // changes any other way, the top step no longer matches and the arrow disappears.
  type InspectorSelection = { nodeId: string | null; edgeId: string | null };
  const [inspectorHistory, setInspectorHistory] = useState<Array<{ from: InspectorSelection; to: InspectorSelection }>>([]);
  const sameSelection = (a: InspectorSelection, b: InspectorSelection) => a.nodeId === b.nodeId && a.edgeId === b.edgeId;
  const currentSelection: InspectorSelection = { nodeId: selectedNodeId, edgeId: selectedEdgeId };
  const inspectorBack = inspectorHistory.length > 0 && sameSelection(inspectorHistory[inspectorHistory.length - 1].to, currentSelection)
    ? inspectorHistory[inspectorHistory.length - 1] : null;
  const navigateInspector = (to: InspectorSelection) => {
    const step = { from: currentSelection, to };
    setInspectorHistory(history => inspectorBack ? [...history, step] : [step]);
    setSelectedNodeId(to.nodeId);
    setSelectedEdgeId(to.edgeId);
  };
  const goInspectorBack = () => {
    if (!inspectorBack) return;
    setInspectorHistory(history => history.slice(0, -1));
    setSelectedNodeId(inspectorBack.from.nodeId);
    setSelectedEdgeId(inspectorBack.from.edgeId);
  };

  // Both a selection and an explicit focus dim the graph. Reset them together
  // so clearing one cannot leave the other highlighting the same neighborhood.
  const clearGraphHighlight = useCallback(() => {
    setFocusNodeId(null);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
  }, []);

  const handleZoomIn = () => {
    if (!graphRef.current) return;
    const currentZoom = graphRef.current.zoom();
    graphRef.current.zoom(currentZoom * 1.3, 300);
  };

  const handleZoomOut = () => {
    if (!graphRef.current) return;
    const currentZoom = graphRef.current.zoom();
    graphRef.current.zoom(currentZoom / 1.3, 300);
  };

  // Monitor container size for responsive graph layout
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(entries => {
      const r = entries[0].contentRect;
      setDimensions({ width: Math.floor(r.width), height: Math.floor(r.height) });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // Measure the stable outer panel, not the canvas left over after opening UI.
  // Otherwise switching a drawer/toolbar could change its own breakpoint.
  useEffect(() => {
    if (!panelRef.current) return;
    const observer = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      setPanelSize(previous => previous.width === Math.floor(width) && previous.height === Math.floor(height)
        ? previous : { width: Math.floor(width), height: Math.floor(height) });
    });
    observer.observe(panelRef.current);
    return () => observer.disconnect();
  }, []);

  const neighborhoodProjectId = useCallback((node: GraphNode): number | null => {
    return node.project_id ?? selectedProject?.id ?? null;
  }, [selectedProject]);

  // In-place expansion edits the overview itself, so the cached overview has to follow along.
  const loadedGraph = useMemo(() => ({ nodes: rawNodes, edges: rawEdges }), [rawNodes, rawEdges]);
  const replaceOverviewGraph = useCallback((graph: GraphData) => {
    const recount = (truncation: { shown: number; total: number; edgesSampled: boolean } | null) => truncation
      && { ...truncation, shown: graph.nodes.length, total: Math.max(truncation.total, graph.nodes.length) };
    setRawNodes(graph.nodes);
    setRawEdges(graph.edges);
    setOverviewTruncation(recount);
    const cached = overviewCacheRef.current;
    if (cached) overviewCacheRef.current = { ...cached, ...graph, truncation: recount(cached.truncation) };
  }, []);
  const expansion = useGraphExpansion({ graph: loadedGraph, setGraph: replaceOverviewGraph, projectIdFor: neighborhoodProjectId });
  const resetExpansions = expansion.reset;

  const loadOverview = useCallback(async (force = false, includeIsolatedOverride?: boolean, keepAnchor?: { node: GraphNode; edges: GraphEdge[] } | null) => {
    /** Loads all approved links of the repository from the backend. */
    const projectId = selectedProject?.id ?? null;
    const includeIsolated = includeIsolatedOverride ?? !onlyLinked;
    const cachedOverview = overviewCacheRef.current;
    if (!force && cachedOverview?.projectId === projectId && cachedOverview?.includeIsolated === includeIsolated) {
      const restored = withKeptAnchor(cachedOverview.nodes, cachedOverview.edges, keepAnchor);
      setRawNodes(restored.nodes);
      setRawEdges(restored.edges);
      setOverviewTruncation(cachedOverview.truncation);
      setViewMode('overview');
      setNeighborhoodFocusNode(null);
      setNeighborhoodCursor(null);
      setNeighborhoodHasMore(false);
      setIsLoadingMore(false);
      setNeighborhoodError(null);
      setSelectedEdgeId(null);
      setLinkFilterResetToken(previous => previous + 1);

      if (keepAnchor) {
        setSelectedNodeId(keepAnchor.node.id);
      } else if (selectedDoc) {
        const docNode = cachedOverview.nodes.find((n: GraphNode) => n.id === `doc:${selectedDoc.url}` || n.label === selectedDoc.name);
        setSelectedNodeId(docNode?.id ?? null);
      } else {
        setSelectedNodeId(null);
      }
      return;
    }

    setIsLoading(true);
    setNeighborhoodError(null);
    try {
      const params = new URLSearchParams({ status: 'approved' });
      if (projectId) params.set('project_id', String(projectId));
      if (includeIsolated) params.set('include_isolated', 'true');
      addFocusParam(params);
      const res = await api.fetch(`${API_URL}/graph?${params}`);
      const data: { nodes?: GraphNode[]; edges?: GraphEdge[]; truncated?: boolean; edges_sampled?: boolean; total_nodes?: number; focus_id?: string } = await res.json();
      const nodes = data.nodes ?? [];
      const edges = data.edges ?? [];
      const truncation = data.truncated
        ? { shown: nodes.length, total: data.total_nodes ?? nodes.length, edgesSampled: Boolean(data.edges_sampled) }
        : null;
      overviewCacheRef.current = { projectId, includeIsolated, nodes, edges, truncation };
      resetExpansions();
      const restored = withKeptAnchor(nodes, edges, keepAnchor);
      setRawNodes(restored.nodes);
      setRawEdges(restored.edges);
      setViewMode('overview');
      setNeighborhoodFocusNode(null);
      setNeighborhoodCursor(null);
      setNeighborhoodHasMore(false);
      setIsLoadingMore(false);
      setLinkFilterResetToken(previous => previous + 1);
      // O-053: GET /graph caps at KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES for large
      // projects and reports the true totals alongside the (possibly smaller)
      // returned set -- surfaced as a banner, see truncatedOverviewNotice below.
      setOverviewTruncation(truncation);

      // Auto-select document node if active
      if (keepAnchor) {
        setSelectedNodeId(keepAnchor.node.id);
      } else if (selectedDoc) {
        const docNode = nodes.find((n: GraphNode) => n.id === `doc:${selectedDoc.url}` || n.label === selectedDoc.name);
        if (docNode) setSelectedNodeId(docNode.id);
        else setSelectedNodeId(null);
      } else {
        setSelectedNodeId(null);
      }
      setSelectedEdgeId(null);
    } catch (e) {
      console.error('[KnowledgeGraph] load failed', e);
    } finally {
      setIsLoading(false);
    }
  }, [selectedProject, selectedDoc, onlyLinked, addFocusParam, resetExpansions]);

  const loadNeighborhood = useCallback(async (node: GraphNode, focusOptions?: AgentGraphViewAction['target']) => {
    /**
     * O-053 / O-298: hard focus / neighborhood -- fetches this node's actual one-hop
     * neighborhood via GET /graph/focus (for entities) or GET /graph/neighborhood (for docs)
     * instead of dimming whatever happens to be in the already-loaded overview.
     * Supports cursor-based expansion (has_more, next_cursor).
     */
    const isDoc = node.type === 'document' || node.id.startsWith('doc:');
    const isFile = node.type === 'code_file' || node.id.startsWith('file:');
    const entityDbId = isDoc ? null : extractEntityDbId(node.id);
    const projectId = neighborhoodProjectId(node);
    const relationships = focusOptions?.relationships ?? ['code_dependency', 'documented', 'manual'];
    const limit = focusOptions?.limit ?? 150;
    const direction = focusOptions?.direction ?? traversalDirection;
    const hops = focusOptions?.hops ?? traversalHops;
    if (!isDoc && !isFile && (entityDbId === null || projectId === null)) {
      setNeighborhoodError(t('knowledgeGraphView.loadNeighborhoodUnavailable'));
      return;
    }
    setIsLoadingNeighborhood(true);
    setNeighborhoodError(null);
    try {
      let res: Response;
      if (isDoc || isFile) {
        const params = new URLSearchParams({
          node_id: node.id,
          status: 'approved',
          relationships: relationships.join(','),
          direction,
          limit: String(limit),
        });
        if (projectId !== null) params.set('project_id', String(projectId));
        res = await api.fetch(`${API_URL}/graph/neighborhood?${params}`);
      } else {
        const params = new URLSearchParams({
          status: 'approved', project_id: String(projectId), entity_id: String(entityDbId),
          direction, hops: String(hops),
        });
        res = await api.fetch(`${API_URL}/graph/focus?${params}`);
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: {
        nodes?: GraphNode[];
        edges?: GraphEdge[];
        truncated?: boolean | { incoming?: boolean; outgoing?: boolean };
        total_nodes?: number;
        focus_id?: string;
        has_more?: boolean;
        next_cursor?: string | null;
      } = await res.json();
      setRawNodes(data.nodes ?? []);
      setRawEdges(data.edges ?? []);
      setViewMode('neighborhood');
      setNeighborhoodFocusNode(node);
      setNeighborhoodHasMore(Boolean(data.has_more));
      setNeighborhoodCursor(data.next_cursor ?? null);
      setNeighborhoodRelationships(relationships);
      setNeighborhoodLimit(limit);
      setTraversalDirection(direction);
      setTraversalHops(hops);
      setLinkFilterResetToken(previous => previous + 1);
      setOverviewTruncation(null);
      setSelectedNodeId(data.focus_id ?? node.id);
      setSelectedEdgeId(null);
      setFocusNodeId(null);
    } catch (e) {
      console.error('[KnowledgeGraph] neighborhood load failed', e);
      setNeighborhoodError(t('knowledgeGraphView.loadNeighborhoodError'));
    } finally {
      setIsLoadingNeighborhood(false);
    }
  }, [neighborhoodProjectId, t, traversalDirection, traversalHops]);

  const handleBackToOverview = () => {
    const anchor = neighborhoodFocusNode;
    if (!anchor) {
      void loadOverview();
      return;
    }
    const touchesAnchor = (end: GraphEdge['source']) => (typeof end === 'object' ? end.id : end) === anchor.id;
    void loadOverview(false, undefined, {
      node: anchor,
      edges: rawEdges.filter(e => touchesAnchor(e.source) || touchesAnchor(e.target)),
    });
  };

  const loadMoreConnections = useCallback(async () => {
    if (!neighborhoodFocusNode || !neighborhoodCursor || isLoadingMore) return;
    setIsLoadingMore(true);
    setNeighborhoodError(null);
    try {
      const isDoc = neighborhoodFocusNode.type === 'document' || neighborhoodFocusNode.id.startsWith('doc:');
      const isFile = neighborhoodFocusNode.type === 'code_file' || neighborhoodFocusNode.id.startsWith('file:');
      const entityDbId = isDoc ? null : extractEntityDbId(neighborhoodFocusNode.id);
      const projectId = neighborhoodProjectId(neighborhoodFocusNode);
      let res: Response;
      if (isDoc || isFile) {
        const params = new URLSearchParams({
          node_id: neighborhoodFocusNode.id,
          status: 'approved',
          cursor: neighborhoodCursor,
          relationships: neighborhoodRelationships.join(','),
          direction: traversalDirection,
          limit: String(neighborhoodLimit),
        });
        if (projectId !== null) params.set('project_id', String(projectId));
        res = await api.fetch(`${API_URL}/graph/neighborhood?${params}`);
      } else {
        const params = new URLSearchParams({
          project_id: String(projectId),
          entity_id: String(entityDbId),
          status: 'approved',
          cursor: neighborhoodCursor,
          direction: traversalDirection,
          hops: String(traversalHops),
        });
        res = await api.fetch(`${API_URL}/graph/focus?${params}`);
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: {
        nodes?: GraphNode[];
        edges?: GraphEdge[];
        has_more?: boolean;
        next_cursor?: string | null;
      } = await res.json();

      setRawNodes(prev => {
        const existing = new Set(prev.map(n => n.id));
        const additions = (data.nodes ?? []).filter(n => !existing.has(n.id));
        return additions.length > 0 ? [...prev, ...additions] : prev;
      });
      setRawEdges(prev => {
        const existing = new Set(prev.map(e => e.id));
        const additions = (data.edges ?? []).filter(e => !existing.has(e.id));
        return additions.length > 0 ? [...prev, ...additions] : prev;
      });
      setNeighborhoodHasMore(Boolean(data.has_more));
      setNeighborhoodCursor(data.next_cursor ?? null);
    } catch (e) {
      console.error('[KnowledgeGraph] load more connections failed', e);
      setNeighborhoodError(t('knowledgeGraphView.loadNeighborhoodError'));
    } finally {
      setIsLoadingMore(false);
    }
  }, [neighborhoodFocusNode, neighborhoodCursor, isLoadingMore, neighborhoodProjectId, neighborhoodRelationships, neighborhoodLimit, t, traversalDirection, traversalHops]);

  const closeLinkPicker = useCallback(() => {
    setIsLinkPickerOpen(false);
    setLinkPickerTargetId(null);
    setLinkDescription('');
    setLinkCreateError(null);
  }, []);

  useEffect(() => {
    if (!isLinkPickerOpen) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') closeLinkPicker(); };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [isLinkPickerOpen, closeLinkPicker]);

  const createManualLink = useCallback(async (sourceNode: GraphNode, targetNode: GraphNode) => {
    /** Connects two currently-loaded nodes via a manual KnowledgeLink (see backend/api/knowledge_links.py). */
    if (!sourceNode || !targetNode || sourceNode.id === targetNode.id) return;
    const sideFromNode = (n: GraphNode) => {
      if (n.type === 'entity' || n.type === 'code_file') {
        const numId = n.type === 'entity'
          ? parseInt(n.id.slice('entity:'.length), 10)
          : n.entity_ids?.[0];
        return { type: 'entity', entity_id: Number.isNaN(numId) ? null : numId, title: n.label, url: n.url ?? null, source_type: n.entity_type ?? null };
      }
      return { type: 'document', entity_id: null, title: n.label, url: n.url ?? null, source_type: n.source_type ?? null };
    };
    const a = sideFromNode(sourceNode);
    const b = sideFromNode(targetNode);
    setIsCreatingLink(true);
    setLinkCreateError(null);
    try {
      const res = await api.fetch(`${API_URL}/knowledge-links`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_a_type: a.type, source_a_entity_id: a.entity_id, source_a_title: a.title, source_a_url: a.url, source_a_source_type: a.source_type,
          source_b_type: b.type, source_b_entity_id: b.entity_id, source_b_title: b.title, source_b_url: b.url, source_b_source_type: b.source_type,
          link_type: 'manual', direction: manualLinkDirection, status: 'approved',
          context: linkDescription.trim() || null,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRawEdges(prev => [...prev, {
        id: `kl:${data.id}`,
        source: sourceNode.id,
        target: targetNode.id,
        link_type: 'manual',
        direction: manualLinkDirection,
        score: null,
        context: linkDescription.trim() || null,
      }]);
      setIsLinkPickerOpen(false);
      setLinkPickerQuery('');
      setLinkPickerTargetId(null);
      setLinkDescription('');
      setManualLinkDirection('undirected');
    } catch (e) {
      console.error('[KnowledgeGraph] manual link creation failed', e);
      setLinkCreateError(t('knowledgeGraphView.createLinkError'));
    } finally {
      setIsCreatingLink(false);
    }
  }, [t, manualLinkDirection, linkDescription]);

  // Reset the link-creation picker whenever the selection changes so it doesn't
  // linger open/stale against a now-different node. Done during render
  // (guarded by a state comparison) rather than in an effect, since these are
  // otherwise user-controlled (see the picker's own buttons below).
  const [prevSelectedNodeIdForPicker, setPrevSelectedNodeIdForPicker] = useState(selectedNodeId);
  if (selectedNodeId !== prevSelectedNodeIdForPicker) {
    setPrevSelectedNodeIdForPicker(selectedNodeId);
    setIsLinkPickerOpen(false);
    setLinkPickerQuery('');
    setLinkPickerTargetId(null);
    setLinkDescription('');
    setLinkCreateError(null);
  }

  // Repo-Wechsel: Fokus zurücksetzen (während des Renders, s.o. — focusNodeId
  // ist sonst über Klicks im Graph user-gesteuert).
  const [prevProjectIdForFocus, setPrevProjectIdForFocus] = useState(selectedProject?.id ?? null);
  if ((selectedProject?.id ?? null) !== prevProjectIdForFocus) {
    setPrevProjectIdForFocus(selectedProject?.id ?? null);
    setFocusNodeId(null);
  }

  // Externe Auswahl (Sidebar, Editor, Docs) -> Fokus setzen/aufheben. Ebenfalls
  // während des Renders statt in einem Effekt (gleicher Grund wie oben).
  const [prevFocusDeps, setPrevFocusDeps] = useState({ selectedEntity, selectedFile, selectedDoc, projectEntities });
  if (
    prevFocusDeps.selectedEntity !== selectedEntity ||
    prevFocusDeps.selectedFile !== selectedFile ||
    prevFocusDeps.selectedDoc !== selectedDoc ||
    prevFocusDeps.projectEntities !== projectEntities
  ) {
    setPrevFocusDeps({ selectedEntity, selectedFile, selectedDoc, projectEntities });

    // 1. Entity Fokus (Höchste Priorität). Ein `selectedEntity` ohne auflösbare ID
    // (z.B. der Rückkanal eines simplen Node-Klicks im Graph selbst, der bewusst
    // keine ID mitschickt) muss hier stoppen — sonst kaskadiert es in den
    // File-Fallback unten und fokussiert die falsche Entity (irgendeine andere
    // im selben file_path, nicht die tatsächlich gemeinte).
    if (selectedEntity) {
      const entId = extractEntityDbId(selectedEntity.id);
      if (entId != null) {
        setFocusNodeId(`entity:${entId}`);
      }
    } else if (selectedFile) {
      // 2. File Fallback (Erste Entity der Datei fokussieren)
      const fileEnts = projectEntities.filter(e => e.file_path === selectedFile);
      let focused = false;
      if (fileEnts.length > 0) {
        const entId = extractEntityDbId(fileEnts[0].id);
        if (entId != null) {
          setFocusNodeId(`entity:${entId}`);
          focused = true;
        }
      }
      if (!focused) setFocusNodeId(null);
    } else if (selectedDoc) {
      // 3. Document Fallback (Fokus aufheben, Node nur selektieren)
      setFocusNodeId(null);
    }
  }

  // An agent request, load the real bounded neighborhood directly. The action
  // target contains a server-validated graph node ID; no free-form path is used.
  useEffect(() => {
    if (agentGraphFocus) return;
    resetFocus();
    void loadOverview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProject?.id]);

  const lastAgentGraphFocusKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (!agentGraphFocus) {
      lastAgentGraphFocusKeyRef.current = null;
      return;
    }
    const requestKey = `${selectedProject?.id ?? 'none'}:${JSON.stringify(agentGraphFocus)}`;
    if (lastAgentGraphFocusKeyRef.current === requestKey) return;
    lastAgentGraphFocusKeyRef.current = requestKey;
    const isDocumentNode = agentGraphFocus.focus_id.startsWith('doc:');
    const focusNode: GraphNode = {
      id: agentGraphFocus.focus_id,
      type: isDocumentNode ? 'document' : 'code_file',
      label: agentGraphFocus.focus_label,
      project_id: selectedProject?.id,
    };
    void loadNeighborhood(focusNode, agentGraphFocus);
    // The request key prevents state changes inside loadNeighborhood from
    // repeating the same agent action.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProject?.id, agentGraphFocus]);

  // Sync selectedNodeId based on external props changes (selectedDoc, selectedFile,
  // selectedEntity). During render, same reasoning as the focus sync above.
  const [prevSelectedNodeIdDeps, setPrevSelectedNodeIdDeps] = useState({ selectedEntity, selectedDoc, selectedFile, rawNodes });
  if (
    prevSelectedNodeIdDeps.selectedEntity !== selectedEntity ||
    prevSelectedNodeIdDeps.selectedDoc !== selectedDoc ||
    prevSelectedNodeIdDeps.selectedFile !== selectedFile ||
    prevSelectedNodeIdDeps.rawNodes !== rawNodes
  ) {
    setPrevSelectedNodeIdDeps({ selectedEntity, selectedDoc, selectedFile, rawNodes });

    if (selectedEntity) {
      const fileNode = rawNodes.find((n: GraphNode) =>
        n.type === 'code_file' && n.file_path === selectedEntity.file_path &&
        (selectedEntity.source_id == null || n.source_id === selectedEntity.source_id),
      );
      if (fileNode) setSelectedNodeId(fileNode.id);
    } else if (selectedDoc) {
      const docNode = rawNodes.find((n: GraphNode) => n.id === `doc:${selectedDoc.url}` || n.label === selectedDoc.name);
      if (docNode) setSelectedNodeId(docNode.id);
    } else if (selectedFile) {
      const fileNode = rawNodes.find((n: GraphNode) => n.id === `doc:${selectedFile}` || n.label === selectedFile || n.url === selectedFile);
      if (fileNode) {
        setSelectedNodeId(fileNode.id);
      } else {
        const entNode = rawNodes.find((n: GraphNode) => n.type === 'code_file' && n.file_path === selectedFile);
        if (entNode) setSelectedNodeId(entNode.id);
      }
    }
  }

  // Filtered data for the graph
  const filteredData = useMemo(() => createGraphScene(filterVisibleGraph(rawNodes, rawEdges, {
    isNodeHidden: n => hiddenNodeTypes.has(nodeTypeKey(n)),
    isEdgeHidden: e => hiddenLinkTypes.has(graphEdgeType(e)) || hiddenEdgeDirections.has(graphEdgeDirection(e)),
    onlyLinked,
  })), [rawNodes, rawEdges, hiddenNodeTypes, hiddenLinkTypes, hiddenEdgeDirections, onlyLinked]);
  const { ghostIds } = filteredData;

  const nodeDegrees = useMemo(() => {
    const degrees = new Map<string, number>();
    for (const edge of filteredData.links) {
      const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
      const targetId = typeof edge.target === 'object' ? edge.target.id : edge.target;
      degrees.set(sourceId, (degrees.get(sourceId) ?? 0) + 1);
      degrees.set(targetId, (degrees.get(targetId) ?? 0) + 1);
    }
    // Size follows the real number of connections, not only the loaded ones.
    for (const node of filteredData.nodes) {
      if ((node.degree ?? 0) > (degrees.get(node.id) ?? 0)) degrees.set(node.id, node.degree!);
    }
    return degrees;
  }, [filteredData.nodes, filteredData.links]);
  const hiddenCounts = useMemo(() => viewMode === 'overview' ? hiddenEdgeCounts(rawNodes, rawEdges) : new Map<string, number>(),
    [viewMode, rawNodes, rawEdges]);

  // Von außen gesetzter Fokus (z. B. Suchtreffer): nur zentrieren, der Zoom bleibt. Ein Klick im
  // Graph setzt den Fokus nicht, dort bewegt sich die Kamera nicht.
  useEffect(() => {
    if (!focusNodeId) return;
    const timer = setTimeout(() => {
      const node = filteredData.nodes.find((n: GraphNode) => n.id === focusNodeId);
      if (node && node.x !== undefined && node.y !== undefined) graphRef.current?.centerAt(node.x, node.y, 600);
    }, 350);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusNodeId]);

  // Keine Kamerabewegung bei der Auswahl: Zoom und Ausschnitt bleiben, nur die Hervorhebung
  // (Ausgrauen der übrigen Knoten) ändert sich.

  // Available node/link types for filter chips
  const nodeTypes = useMemo(() => {
    const s = new Set<string>();
    rawNodes.forEach(n => s.add(nodeTypeKey(n)));
    return Array.from(s);
  }, [rawNodes]);

  const linkTypes = useMemo(() => {
    const s = new Set<string>();
    rawEdges.forEach(e => s.add(graphEdgeType(e)));
    return Array.from(s);
  }, [rawEdges]);

  const edgeDirections = useMemo(() => {
    const directions = new Set<GraphEdgeDirection>();
    rawEdges.forEach(edge => directions.add(graphEdgeDirection(edge)));
    return Array.from(directions);
  }, [rawEdges]);

  // A freshly loaded knowledge graph starts with every relationship family
  // visible. The backend already collapses parser-specific code edge types into
  // one bounded code_dependency family.
  const lastLinkFilterResetRef = useRef<string | null>(null);
  useEffect(() => {
    if (linkTypes.length === 0) return;
    const filterKey = `${selectedProject?.id ?? 'general'}:${linkFilterResetToken}`;
    if (lastLinkFilterResetRef.current === filterKey) return;
    lastLinkFilterResetRef.current = filterKey;
    setHiddenLinkTypes(new Set());
    setHiddenEdgeDirections(new Set());
  }, [linkFilterResetToken, linkTypes, selectedProject?.id]);

  useKnowledgeGraphLayout({ graphRef, ready: !!ForceGraphComponent && !isLoading && dimensions.width > 0,
    nodes: filteredData.nodes, links: filteredData.links, degrees: nodeDegrees,
    mode: viewMode, focusId: neighborhoodFocusNode?.id, direction: traversalDirection });

  // Selecting a node highlights its direct one-hop neighborhood. The current
  // graph selection takes priority over a stale/external focus; when no node is
  // selected, an explicit focusNodeId can keep the neighborhood pinned.
  // Selecting an edge highlights only its endpoints and that edge otherwise.
  const activeFocusNodeId = selectedNodeId ?? focusNodeId;
  const focusNeighborIds = useMemo(() => {
    if (activeFocusNodeId) {
      const ids = new Set<string>([activeFocusNodeId]);
      filteredData.links.forEach((l: GraphEdge) => {
        const src = typeof l.source === 'object' ? l.source.id : l.source;
        const tgt = typeof l.target === 'object' ? l.target.id : l.target;
        if (src === activeFocusNodeId) ids.add(tgt);
        if (tgt === activeFocusNodeId) ids.add(src);
      });
      return ids;
    }
    if (selectedEdgeId) {
      const edge = filteredData.links.find((l: GraphEdge) => l.id === selectedEdgeId);
      if (!edge) return null;
      const src = typeof edge.source === 'object' ? edge.source.id : edge.source;
      const tgt = typeof edge.target === 'object' ? edge.target.id : edge.target;
      return new Set<string>([src, tgt]);
    }
    return null;
  }, [activeFocusNodeId, selectedEdgeId, filteredData]);

  const selectedNode = useMemo(() => filteredData.nodes.find(n => n.id === selectedNodeId) ?? rawNodes.find(n => n.id === selectedNodeId) ?? null, [filteredData.nodes, rawNodes, selectedNodeId]);
  const selectedEdge = useMemo(() => rawEdges.find(e => e.id === selectedEdgeId) ?? null, [rawEdges, selectedEdgeId]);

  const zoomRef = useRef(1);
  const viewportRef = useRef<GraphViewport | null>(null);
  const styleRevision = useGraphStyleRevision();
  // The factory captures getters; only Canvas/event callbacks invoke them.
  // eslint-disable-next-line react-hooks/refs
  const renderer = useMemo(() => createKnowledgeGraphRenderer({
    nodes: filteredData.nodes, links: filteredData.links, degrees: nodeDegrees, ghostIds,
    selectedNodeId, selectedEdgeId, focusNodeId, focusNeighborIds, isDark, hiddenCounts,
    viewport: () => viewportRef.current, zoom: () => zoomRef.current,
    // The subscription invalidates colors after parent effects apply theme CSS.
    styleRevision,
  }), [filteredData, nodeDegrees, ghostIds, selectedNodeId, selectedEdgeId, focusNodeId, focusNeighborIds, isDark, hiddenCounts, styleRevision]);
  const updateViewport = useCallback(() => {
    const graph = graphRef.current;
    if (!graph?.screen2GraphCoords) return;
    const center = graph.screen2GraphCoords(dimensions.width / 2, dimensions.height / 2);
    const k = graph.zoom();
    zoomRef.current = k;
    viewportRef.current = { x: center.x, y: center.y, k, ...dimensions };
  }, [dimensions]);

  // Shared by the click handlers below and the sidebar's "open" action so they
  // resolve a document/external node's file + source id identically. The graph
  // node IDs identify source-native resources; source_id remains the connector ID.
  // node.label is the connector's *relative* title (see parser/connectors/folder.py:
  // `title=rel_path`), which 404s against the backend's file
  // lookup for any folder-scanned source — only node.file_path (the real absolute
  // path, set from `storage_key` in diesen Connectoren) resolves. Confluence/Jira
  // store non-path strings (issue key, page title) as their storage_key, so those
  // keep using url/label instead.
  const isWebOriginSourceType = (sourceType: string | null | undefined) =>
    !!sourceType && ['confluence', 'notion', 'jira'].includes(sourceType.toLowerCase());

  // Nicht geladene Verbindungen eines Knotens: in die Übersicht einblenden und wieder einklappen.
  const renderExpansionControls = (node: GraphNode) => {
    if (viewMode !== 'overview' || !canExpandInPlace(node)) return null;
    const hidden = hiddenCounts.get(node.id) ?? 0;
    const expanded = expansion.expansions.get(node.id);
    if (!hidden && !expanded) return null;
    const loading = expansion.loadingId === node.id;
    const actionClass = cn('flex items-center gap-1.5 text-[0.6875rem] transition-colors',
      loading ? 'opacity-50 cursor-not-allowed text-ds-indigo-400' : 'text-ds-indigo-400 hover:text-ds-indigo-300');
    return (
      <div className="mt-2 flex flex-col gap-1.5" data-testid="node-expansion">
        {hidden > 0 && <p className="text-[0.625rem] text-ds-zinc-500">{t('knowledgeGraphView.hiddenConnections', { count: hidden })}</p>}
        {hidden > 0 && (!expanded || expanded.hasMore) && (
          <button onClick={() => void expansion.expand(node, { x: node.x, y: node.y })} disabled={loading}
            title={t('knowledgeGraphView.expandInPlaceTitle')} className={actionClass}>
            {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
            {t(expanded ? 'knowledgeGraphView.expandMore' : 'knowledgeGraphView.expandInPlace')}
          </button>
        )}
        {expanded && (
          <button onClick={() => expansion.collapse(node.id)} disabled={loading} className={actionClass}>
            <Minus className="w-3 h-3" />
            {t('knowledgeGraphView.collapseExpansion')}
          </button>
        )}
        {expansion.errorNodeId === node.id && (
          <p className="flex items-center gap-1.5 text-[0.625rem] text-ds-red-400">
            <AlertTriangle className="w-3 h-3 shrink-0" />
            {t('knowledgeGraphView.loadNeighborhoodError')}
          </p>
        )}
      </div>
    );
  };

  const resolveDocSelector = (node: GraphNode) => {
    const pathVal = (node.file_path && !isWebOriginSourceType(node.source_type))
      ? node.file_path
      : (node.url || node.label);
    return { pathVal, sourceIdVal: node.source_id ?? null };
  };

  const linkPickerCandidates = useMemo(() => {
    if (!selectedNode) return [];
    const q = linkPickerQuery.trim().toLowerCase();
    return rawNodes
      .filter(n => n.id !== selectedNode.id)
      .filter(n => !q || n.label.toLowerCase().includes(q))
      .slice(0, 30);
  }, [rawNodes, selectedNode, linkPickerQuery]);

  // Canvas node drawing — Neo4j style circles with labels
  const toggleNodeType = (type: string) => {
    setHiddenNodeTypes(prev => {
      const next = new Set(prev);
      next.has(type) ? next.delete(type) : next.add(type);
      return next;
    });
  };

  const toggleLinkType = (type: string) => {
    setHiddenLinkTypes(prev => {
      const next = new Set(prev);
      next.has(type) ? next.delete(type) : next.add(type);
      return next;
    });
  };

  const toggleEdgeDirection = (direction: GraphEdgeDirection) => {
    setHiddenEdgeDirections(prev => {
      const next = new Set(prev);
      next.has(direction) ? next.delete(direction) : next.add(direction);
      return next;
    });
  };

  // Layout
  const panelOpen = !!(selectedNode || selectedEdge);
  const compactToolbar = panelSize.width < 700;
  const detailMode = panelSize.width >= 960 ? 'side'
    : panelSize.width >= 460 && panelSize.height >= 560 ? 'bottom' : 'sheet';
  const [detailsExpanded, setDetailsExpanded] = useState<boolean | null>(null);
  // Choose an initial presentation once. Afterwards even an open inspector
  // survives resizing and switching between a side panel, drawer and sheet.
  if (detailsExpanded === null && panelSize.width > 0) setDetailsExpanded(panelSize.width >= 960);
  const showDetails = panelOpen && detailsExpanded && !toolSurface;
  const hiddenFilterCount = nodeTypes.filter(type => hiddenNodeTypes.has(type)).length
    + linkTypes.filter(type => hiddenLinkTypes.has(type)).length
    + edgeDirections.filter(direction => hiddenEdgeDirections.has(direction)).length;
  const selectionLabel = selectedNode ? getNodeDisplayLabel(selectedNode)
    : selectedEdge ? (getLinkLabel(t, graphEdgeType(selectedEdge)) ?? graphEdgeType(selectedEdge)) : '';
  const backNode = inspectorBack?.from.nodeId ? rawNodes.find(n => n.id === inspectorBack.from.nodeId) : undefined;
  const backEdge = inspectorBack?.from.edgeId ? rawEdges.find(e => e.id === inspectorBack.from.edgeId) : undefined;
  const inspectorBackLabel = backNode ? getNodeDisplayLabel(backNode)
    : backEdge ? (getLinkLabel(t, graphEdgeType(backEdge)) ?? graphEdgeType(backEdge)) : '';

  /* ── Theme tokens ───────────────────────────────────────────────────────────── */
  const border     = isDark ? 'border-ds-zinc-800'             : 'border-ds-zinc-200';
  const textMain   = isDark ? 'text-ds-zinc-100'               : 'text-ds-zinc-900';
  const textMuted  = isDark ? 'text-ds-zinc-500'               : 'text-ds-zinc-400';
  const chipBase   = isDark ? 'border-ds-zinc-700 hover:border-ds-zinc-500' : 'border-ds-zinc-300 hover:border-ds-zinc-400';
  const agentDirectionLabel = agentGraphFocus?.direction === 'incoming'
    ? t('knowledgeGraphView.agentDirectionIncoming')
    : agentGraphFocus?.direction === 'outgoing'
      ? t('knowledgeGraphView.agentDirectionOutgoing')
      : t('knowledgeGraphView.agentDirectionBoth');
  const agentRelationshipLabels = agentGraphFocus?.relationships
    .map(type => getLinkLabel(t, type) ?? type)
    .join(', ');
  const iconBtn    = isDark ? 'text-ds-zinc-500 hover:text-ds-zinc-200 hover:bg-ds-zinc-800' : 'text-ds-zinc-400 hover:text-ds-zinc-700 hover:bg-ds-zinc-100';
  const badge      = isDark ? 'bg-ds-zinc-800 text-ds-zinc-400'  : 'bg-ds-zinc-100 text-ds-zinc-500';
  const connRow    = isDark ? 'hover:bg-ds-zinc-800/60'        : 'hover:bg-ds-zinc-50';
  const graphBg    = resolveDsColor(isDark ? 'rgb(var(--ds-neutral-800))' : 'rgb(var(--ds-neutral-100))');

  /* ── Helpers for detail panel ───────────────────────────────────────────────── */
  function resolveNode(ref: string | GraphNode | null | undefined): GraphNode | undefined {
    if (!ref) return undefined;
    if (typeof ref === 'object') return ref as GraphNode;
    return filteredData.nodes.find(n => n.id === ref);
  }

  const edgeSrc = selectedEdge ? resolveNode(selectedEdge.source) : undefined;
  const edgeTgt = selectedEdge ? resolveNode(selectedEdge.target) : undefined;
  const selectedEdgeLocation = selectedEdge
    ? selectedEdge.document_section
      || (selectedEdge.document_page != null ? t('knowledgeGraphView.pageValue', { page: selectedEdge.document_page }) : null)
      || (selectedEdge.document_start_line != null
        ? t('knowledgeGraphView.lineValue', {
            start: selectedEdge.document_start_line,
            end: selectedEdge.document_end_line ?? selectedEdge.document_start_line,
          })
        : null)
      || selectedEdge.document_url_anchor
    : null;

  // Shared content for every inspector presentation. The panel header already
  // names the selection; fields and actions stay the same at every size.
  const renderDetailContent = () => (
    <>
      {/* Node detail */}
      {selectedNode && (
        <div className="min-w-0 px-3 py-3 space-y-4 flex-1">
          <div className="space-y-2">
            {selectedNode.entity_type && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[0.625rem] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.typeLabel')}</span>
                <span className={cn('text-[0.625rem] px-1.5 py-0.5 rounded', badge)}>
                  {getEntityTypeLabel(selectedNode.entity_type, language)}
                </span>
              </div>
            )}
            <InsightGraphDetails node={selectedNode} />
            {selectedNode.language && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[0.625rem] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.languageLabel')}</span>
                <span className={cn('text-[0.625rem] px-1.5 py-0.5 rounded', badge)}>{selectedNode.language}</span>
              </div>
            )}
            {selectedNode.analysis_status && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[0.625rem] w-14 shrink-0', textMuted)}>{t('provenance.analysisStatusLabel')}</span>
                <span
                  className={cn('text-[0.625rem] px-1.5 py-0.5 rounded', badge)}
                  title={selectedNode.analysis_reasons?.join('; ')}
                >
                  {t(`analysisStatus.${selectedNode.analysis_status}`)}
                </span>
              </div>
            )}
            {selectedNode.file_path && (selectedNode.type === 'entity' || selectedNode.type === 'code_file') && (
              selectedNode.type === 'code_file' ? (
                <div className="flex min-w-0 items-baseline gap-2">
                  <span className={cn('text-[0.625rem] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.fileLabel')}</span>
                  <span
                    className={cn('min-w-0 flex-1 truncate text-[0.625rem] font-mono leading-snug', textMain)}
                    title={selectedNode.file_path}
                  >
                    {selectedNode.file_path}
                  </span>
                </div>
              ) : (
                <div className="flex items-baseline gap-2">
                  <span className={cn('text-[0.625rem] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.fileLabel')}</span>
                  <span className={cn('text-[0.625rem] font-mono break-all leading-snug', textMain)}>
                    {selectedNode.file_path}{selectedNode.start_line ? `:${selectedNode.start_line}` : ''}
                  </span>
                </div>
              )
            )}
            {selectedNode.source_type && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[0.625rem] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.sourceLabel')}</span>
                <span className={cn('text-[0.625rem] px-1.5 py-0.5 rounded', badge)}>
                  {selectedNode.source_type}
                </span>
              </div>
            )}
            {selectedNode.resource_type && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[0.625rem] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.resourceLabel')}</span>
                <span className={cn('text-[0.625rem] px-1.5 py-0.5 rounded', badge)}>
                  {t(`knowledgeGraphView.resourceTypes.${selectedNode.resource_type}`)}
                </span>
              </div>
            )}
            {selectedNode.type === 'external' && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[0.625rem] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.statusLabel')}</span>
                <span className="text-[0.625rem] px-1.5 py-0.5 rounded bg-ds-zinc-500/15 text-ds-zinc-400 border border-ds-zinc-500/25">
                  {t('knowledgeGraphView.notFoundInProject')}
                </span>
              </div>
            )}
          </div>

          {/* Connected nodes */}
          <div className={cn('pt-3 border-t', border)}>
            {(() => {
              const nodeLinks = filteredData.links.filter((l: GraphEdge) => {
                const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
                const targetId = typeof l.target === 'object' ? l.target.id : l.target;
                return sourceId === selectedNode.id || targetId === selectedNode.id;
              });
              return (
                <>
                  <p className={cn('text-[0.625rem] font-medium mb-2', textMuted)}>{t('knowledgeGraphView.connectionsLabel')} ({nodeLinks.length})</p>
                  <div className="max-h-56 overflow-y-auto space-y-0.5 pr-1" data-testid="node-connections">
                    {nodeLinks.map((l: GraphEdge) => {
                      const src = resolveNode(l.source);
                      const tgt = resolveNode(l.target);
                      const other = src?.id === selectedNode.id ? tgt : src;
                      if (!other) return null;
                      return (
                        <button key={l.id}
                          onClick={() => {
                            // Die Verbindung wird im Graph ausgewählt (Kante hervorgehoben, übrige ausgegraut) und
                            // in den Ausschnitt gerückt; der Zoom bleibt. Der Zurück-Pfeil führt zum Knoten.
                            navigateInspector({ nodeId: null, edgeId: l.id });
                            if (src && tgt && src.x != null && src.y != null && tgt.x != null && tgt.y != null) {
                              graphRef.current?.centerAt((src.x + tgt.x) / 2, (src.y + tgt.y) / 2, 500);
                            }
                          }}
                          title={getLinkLabel(t, graphEdgeType(l)) ?? graphEdgeType(l)}
                          className={cn('w-full text-left flex items-center gap-2 px-1.5 py-1 rounded text-[0.625rem] transition-colors', connRow)}>
                          <span className="w-3 shrink-0" style={{ height: 2, background: getGraphEdgeColor(graphEdgeType(l)), display: 'inline-block', borderRadius: 1 }} />
                          <span className={cn('truncate', textMain)}>{other.label}</span>
                        </button>
                      );
                    })}
                  </div>
                  {renderExpansionControls(selectedNode)}
                </>
              );
            })()}
          </div>

          {/* Aktionen */}
          <div className="flex flex-col gap-2">
            {(selectedNode.type === 'entity' || selectedNode.type === 'code_file') && selectedNode.file_path && onFileSelect && (
              <button
                onClick={() => {
                  onFileSelect(selectedNode.file_path!, selectedNode.start_line ?? null, selectedNode.source_id ?? null);
                  if (selectedNode.type === 'entity') onEntitySelect?.({
                    name: selectedNode.label,
                    type: selectedNode.entity_type,
                    id: extractEntityDbId(selectedNode.id) ?? undefined,
                    file_path: selectedNode.file_path || '',
                    start_line: selectedNode.start_line ?? 1,
                  });
                }}
                className="flex items-center gap-1.5 text-[0.6875rem] text-ds-indigo-400 hover:text-ds-indigo-300 transition-colors">
                <ExternalLink className="w-3 h-3" />
                {t('knowledgeGraphView.openInView')}
              </button>
            )}

            {(selectedNode.type === 'document' || selectedNode.type === 'external') && onFileSelect && (
              <button
                onClick={() => {
                  const { pathVal, sourceIdVal } = resolveDocSelector(selectedNode);
                  // O-091: exactly one navigation call. This used to also fire
                  // onDocFocus, which decided the target view a second time and
                  // independently -- a document node named SRC/X.cbl then opened
                  // BOTH a code editor (decided by extension) and a doc panel
                  // (decided unconditionally), and the doc selection blanked the
                  // editor again. handlePanelFileSelect classifies doc, webview
                  // and code alike, so the single call covers all three.
                  onFileSelect(pathVal, null, sourceIdVal);
                }}
                className="flex items-center gap-1.5 text-[0.6875rem] text-ds-indigo-400 hover:text-ds-indigo-300 transition-colors">
                <ExternalLink className="w-3 h-3" />
                {t('knowledgeGraphView.openInView')}
              </button>
            )}

            {selectedNode.id !== focusNodeId && (
              <button
                onClick={() => setFocusNodeId(selectedNode.id)}
                className="flex items-center gap-1.5 text-[0.6875rem] text-ds-indigo-400 hover:text-ds-indigo-300 transition-colors">
                <Workflow className="w-3 h-3" />
                {t('knowledgeGraphView.focusOnNode')}
              </button>
            )}

            {((selectedNode.type === 'entity' || selectedNode.type === 'code_file') && neighborhoodProjectId(selectedNode) !== null || selectedNode.type === 'document' || selectedNode.id.startsWith('doc:')) && (
              <div className="flex flex-wrap items-center gap-1.5">
                {selectedNode.type === 'entity' && (
                  <>
                    <select
                      value={traversalDirection}
                      onChange={event => setTraversalDirection(event.target.value as 'incoming' | 'outgoing' | 'both')}
                      aria-label={t('knowledgeGraphView.traversalDirectionLabel')}
                      className={cn('rounded border px-1 py-0.5 text-[0.625rem]', chipBase, isDark ? 'bg-ds-zinc-900' : 'bg-ds-white')}>
                      <option value="incoming">{t('knowledgeGraphView.traversalIncoming')}</option>
                      <option value="outgoing">{t('knowledgeGraphView.traversalOutgoing')}</option>
                      <option value="both">{t('knowledgeGraphView.traversalBoth')}</option>
                    </select>
                    <select
                      value={traversalHops}
                      onChange={event => setTraversalHops(Number(event.target.value) as 1 | 2 | 3 | 4 | 5)}
                      aria-label={t('knowledgeGraphView.traversalHopsLabel')}
                      className={cn('rounded border px-1 py-0.5 text-[0.625rem]', chipBase, isDark ? 'bg-ds-zinc-900' : 'bg-ds-white')}>
                      {[1, 2, 3, 4, 5].map(hop => <option key={hop} value={hop}>{t('knowledgeGraphView.traversalHops', { count: hop })}</option>)}
                    </select>
                  </>
                )}
                <button
                  onClick={() => loadNeighborhood(selectedNode)}
                  disabled={isLoadingNeighborhood}
                  title={t('knowledgeGraphView.loadNeighborhoodTitle')}
                  className={cn('flex items-center gap-1.5 text-[0.6875rem] transition-colors',
                    isLoadingNeighborhood ? 'opacity-50 cursor-not-allowed text-ds-indigo-400' : 'text-ds-indigo-400 hover:text-ds-indigo-300')}>
                  {isLoadingNeighborhood ? <Loader2 className="w-3 h-3 animate-spin" /> : <Crosshair className="w-3 h-3" />}
                  {t('knowledgeGraphView.loadNeighborhood')}
                </button>
              </div>
            )}

            {viewMode === 'neighborhood' && selectedNode.id === neighborhoodFocusNode?.id && neighborhoodHasMore && (
              <button
                onClick={loadMoreConnections}
                disabled={isLoadingMore}
                title={t('knowledgeGraphView.loadMoreConnectionsTitle')}
                className={cn('flex items-center gap-1.5 text-[0.6875rem] transition-colors',
                  isLoadingMore ? 'opacity-50 cursor-not-allowed text-ds-indigo-400' : 'text-ds-indigo-400 hover:text-ds-indigo-300')}>
                {isLoadingMore ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
                {t('knowledgeGraphView.loadMoreConnections')}
              </button>
            )}

            <button
              disabled={selectedNode.type === 'code_file' && !selectedNode.entity_ids?.length}
              onClick={() => { setIsLinkPickerOpen(o => !o); setLinkCreateError(null); }}
              className={cn('flex items-center gap-1.5 text-[0.6875rem] transition-colors',
                selectedNode.type === 'code_file' && !selectedNode.entity_ids?.length
                  ? 'opacity-40 cursor-not-allowed text-ds-zinc-500'
                  : 'text-ds-indigo-400 hover:text-ds-indigo-300')}>
              <Link2 className="w-3 h-3" />
              {t('knowledgeGraphView.createLink')}
            </button>

            {isLinkPickerOpen && typeof document !== 'undefined' && createPortal(
              <div
                className="fixed inset-0 z-[110] flex items-center justify-center bg-ds-black/70 p-4 backdrop-blur-sm"
                onMouseDown={(event) => { if (event.target === event.currentTarget) closeLinkPicker(); }}
              >
              <div
                role="dialog"
                aria-modal="true"
                aria-label={t('knowledgeGraphView.createLink')}
                className={cn('flex max-h-[85vh] w-full max-w-lg flex-col gap-3 rounded-lg border p-5 shadow-2xl', border, isDark ? 'bg-ds-zinc-900 text-ds-zinc-200' : 'bg-ds-white text-ds-zinc-800')}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold">{t('knowledgeGraphView.createLink')}</div>
                    <div className={cn('truncate text-xs', textMuted)}>{selectedNode.label}</div>
                  </div>
                  <button onClick={closeLinkPicker} aria-label={t('knowledgeGraphView.createLinkCancel')} className={cn('shrink-0 rounded p-1 transition-colors', textMuted, 'hover:text-ds-zinc-400')}>
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <div className={cn('flex items-center gap-2 rounded border px-2.5 py-2', border, isDark ? 'bg-ds-zinc-950' : 'bg-ds-zinc-50')}>
                  <Search className="w-3.5 h-3.5 shrink-0 text-ds-zinc-500" />
                  <input
                    autoFocus
                    value={linkPickerQuery}
                    onChange={e => { setLinkPickerQuery(e.target.value); setLinkPickerTargetId(null); }}
                    placeholder={t('knowledgeGraphView.createLinkTargetPlaceholder')}
                    className={cn('w-full bg-transparent text-xs outline-none', textMain)}
                  />
                </div>
                <div className="min-h-32 max-h-72 flex-1 overflow-y-auto space-y-0.5">
                  {linkPickerCandidates.map(n => (
                    <button key={n.id}
                      onClick={() => setLinkPickerTargetId(n.id)}
                      className={cn('w-full text-left flex items-center gap-2 px-2 py-1.5 rounded text-xs transition-colors',
                        linkPickerTargetId === n.id ? (isDark ? 'bg-ds-indigo-500/20' : 'bg-ds-indigo-100') : connRow)}>
                      <KnowledgeNodeIcon node={n} className="w-3 h-3 shrink-0 text-ds-indigo-400" />
                      <span className={cn('truncate', textMain)}>{n.label}</span>
                      {linkPickerTargetId === n.id && <Check className="w-3 h-3 shrink-0 text-ds-indigo-400 ml-auto" />}
                    </button>
                  ))}
                  {linkPickerCandidates.length === 0 && (
                    <p className={cn('text-xs px-2 py-1.5', textMuted)}>{t('knowledgeGraphView.createLinkNoMatches')}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <label htmlFor="manual-link-direction" className={cn('text-[0.625rem] shrink-0', textMuted)}>
                    {t('knowledgeGraphView.createLinkDirectionLabel')}
                  </label>
                  <select
                    id="manual-link-direction"
                    value={manualLinkDirection}
                    onChange={event => setManualLinkDirection(event.target.value as GraphEdgeDirection)}
                    className={cn('min-w-0 flex-1 rounded border px-1.5 py-1 text-[0.625rem]', chipBase, isDark ? 'bg-ds-zinc-900 text-ds-zinc-200' : 'bg-ds-white text-ds-zinc-700')}>
                    <option value="undirected">{t(EDGE_DIRECTION_TAXONOMY.undirected.labelKey)}</option>
                    <option value="directed">{t(EDGE_DIRECTION_TAXONOMY.directed.labelKey)}</option>
                    <option value="bidirectional">{t(EDGE_DIRECTION_TAXONOMY.bidirectional.labelKey)}</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label htmlFor="manual-link-description" className={cn('text-xs', textMuted)}>
                    {t('knowledgeGraphView.createLinkDescriptionLabel')}
                  </label>
                  <textarea
                    id="manual-link-description"
                    value={linkDescription}
                    onChange={event => setLinkDescription(event.target.value)}
                    rows={3}
                    maxLength={1000}
                    placeholder={t('knowledgeGraphView.createLinkDescriptionPlaceholder')}
                    className={cn('w-full resize-y rounded border px-2.5 py-2 text-xs outline-none', chipBase, isDark ? 'bg-ds-zinc-950 text-ds-zinc-200 placeholder:text-ds-zinc-500' : 'bg-ds-white text-ds-zinc-700 placeholder:text-ds-zinc-400')}
                  />
                </div>
                {linkCreateError && <p className="text-xs text-ds-red-400">{linkCreateError}</p>}
                <div className="flex items-center gap-2 justify-end">
                  <button onClick={closeLinkPicker}
                    className={cn('text-xs px-3 py-1.5 rounded transition-colors', textMuted, 'hover:text-ds-zinc-400')}>
                    {t('knowledgeGraphView.createLinkCancel')}
                  </button>
                  <button
                    disabled={!linkPickerTargetId || isCreatingLink}
                    onClick={() => {
                      const target = rawNodes.find(n => n.id === linkPickerTargetId);
                      if (target) createManualLink(selectedNode, target);
                    }}
                    className={cn('text-xs px-3 py-1.5 rounded font-medium transition-colors',
                      !linkPickerTargetId || isCreatingLink ? 'opacity-40 cursor-not-allowed bg-ds-indigo-500/40 text-ds-white' : 'bg-ds-indigo-500 hover:bg-ds-indigo-400 text-ds-white')}>
                    {isCreatingLink ? t('knowledgeGraphView.createLinkSaving') : t('knowledgeGraphView.createLinkConfirm')}
                  </button>
                </div>
              </div>
              </div>,
              document.body
            )}

            {selectedNode.url && (
              <a href={selectedNode.url} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-[0.6875rem] text-ds-indigo-400 hover:text-ds-indigo-300 transition-colors">
                <ExternalLink className="w-3 h-3" />
                {t('knowledgeGraphView.openOriginal')}
              </a>
            )}
          </div>
        </div>
      )}

      {/* Edge detail */}
      {selectedEdge && !selectedNode && (
        <div className="px-3 py-3 space-y-4 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="w-5 shrink-0" style={{ height: 2, background: getGraphEdgeColor(graphEdgeType(selectedEdge)), display: 'inline-block', borderRadius: 1 }} />
            <span className={cn('text-[0.625rem] px-1.5 py-0.5 rounded', badge)}>
              {getLinkLabel(t, graphEdgeType(selectedEdge)) ?? graphEdgeType(selectedEdge)}
            </span>
            {graphEdgeDirection(selectedEdge) !== 'directed' && (
              <span className={cn('text-[0.625rem] px-1.5 py-0.5 rounded', badge)}>
                {t(EDGE_DIRECTION_TAXONOMY[graphEdgeDirection(selectedEdge)].labelKey)}
              </span>
            )}
            {selectedEdge.score !== null && (
              <span className="text-[0.625rem] font-mono text-ds-emerald-500">
                {Math.round((selectedEdge.score ?? 0) * 100)}%
              </span>
            )}
          </div>

          {edgeSrc && (
            <div>
              <p className={cn('text-[0.625rem] mb-1', textMuted)}>{t('knowledgeGraphView.fromLabel')}</p>
              <button onClick={() => navigateInspector({ nodeId: edgeSrc.id, edgeId: null })}
                className={cn('w-full text-left flex items-center gap-2 px-1.5 py-1 rounded text-xs transition-colors', connRow)}>
                <KnowledgeNodeIcon node={edgeSrc} className="w-3 h-3 shrink-0 text-ds-indigo-400" />
                <span className={cn('min-w-0 font-medium truncate', textMain)}>{getNodeDisplayLabel(edgeSrc)}</span>
              </button>
            </div>
          )}

          {edgeTgt && (
            <div>
              <p className={cn('text-[0.625rem] mb-1', textMuted)}>{t('knowledgeGraphView.toLabel')}</p>
              <button onClick={() => navigateInspector({ nodeId: edgeTgt.id, edgeId: null })}
                className={cn('w-full text-left flex items-center gap-2 px-1.5 py-1 rounded text-xs transition-colors', connRow)}>
                <KnowledgeNodeIcon node={edgeTgt} className="w-3 h-3 shrink-0 text-ds-indigo-400" />
                <span className={cn('min-w-0 font-medium truncate', textMain)}>{getNodeDisplayLabel(edgeTgt)}</span>
              </button>
            </div>
          )}

          {selectedEdge.context && (
            <div className={cn('box-border min-w-0 w-full max-w-full whitespace-pre-wrap break-words [overflow-wrap:anywhere] p-2 rounded text-[0.625rem] leading-relaxed', isDark ? 'bg-ds-zinc-800 text-ds-zinc-300' : 'bg-ds-zinc-50 text-ds-zinc-600')}>
              {selectedEdge.context}
            </div>
          )}

          {selectedEdgeLocation && (
            <div className="space-y-1">
              <p className={cn('text-[0.625rem]', textMuted)}>{t('knowledgeGraphView.documentLocationLabel')}</p>
              <p className={cn('text-[0.625rem] font-mono break-words', textMain)}>{selectedEdgeLocation}</p>
            </div>
          )}

          {selectedEdge.code_file_path && edgeTgt && onFileSelect && (
            <button
              onClick={() => onFileSelect(
                selectedEdge.code_file_path!,
                selectedEdge.code_start_line ?? null,
                edgeTgt.source_id ?? null,
              )}
              className="flex items-center gap-1.5 text-[0.6875rem] text-ds-indigo-400 hover:text-ds-indigo-300 transition-colors">
              <ExternalLink className="w-3 h-3" />
              {t('knowledgeGraphView.openCodeEvidence')}
            </button>
          )}

          {selectedEdge.relation_type === 'documented' && edgeTgt && onFileSelect && (
            <button
              onClick={() => {
                let path = selectedEdge.document_file_path || selectedEdge.document_url || edgeTgt.url || edgeTgt.label;
                if (selectedEdge.document_url_anchor && !path.includes('#')) {
                  path = `${path}#${selectedEdge.document_url_anchor}`;
                }
                onFileSelect(path, selectedEdge.document_start_line ?? null, selectedEdge.document_source_id ?? edgeTgt.source_id ?? null);
              }}
              className="flex items-center gap-1.5 text-[0.6875rem] text-ds-indigo-400 hover:text-ds-indigo-300 transition-colors">
              <ExternalLink className="w-3 h-3" />
              {t('knowledgeGraphView.openDocumentLocation')}
            </button>
          )}
        </div>
      )}
    </>
  );

  /* ── Render ─────────────────────────────────────────────────────────────────── */


  return (
    <div ref={panelRef} data-testid="knowledge-graph-view" className="flex flex-col h-full min-h-0 min-w-0"
      onKeyDown={event => {
        if (event.key === 'Escape' && toolSurface && !isLinkPickerOpen && !event.defaultPrevented) {
          event.preventDefault();
          closeToolSurface();
        }
      }}>

      {/* Stable controls; the full taxonomy lives in a bounded tool surface. */}
      <div className={cn('shrink-0 border-b', border)} data-testid="graph-toolbar">
        <div className="flex min-w-0 items-center gap-1 px-2 py-1.5">
          <button ref={filterTriggerRef} aria-expanded={toolSurface === 'filters'} aria-label={hiddenFilterCount ? `${t('knowledgeGraphView.filters')}: ${t('knowledgeGraphView.hiddenFilters', { count: hiddenFilterCount })}` : t('knowledgeGraphView.filters')}
            onClick={() => setToolSurface(current => current === 'filters' ? null : 'filters')}
            className={cn('flex h-7 shrink-0 items-center gap-1 rounded-md border px-2 text-xs', chipBase, toolSurface === 'filters' && 'text-ds-indigo-400')}>
            <SlidersHorizontal className="h-3.5 w-3.5" />
            {t('knowledgeGraphView.filters')}
            {hiddenFilterCount > 0 && <span className="rounded bg-ds-indigo-500/20 px-1 text-ds-indigo-400" title={t('knowledgeGraphView.hiddenFilters', { count: hiddenFilterCount })}>{hiddenFilterCount}</span>}
          </button>
          <div className="min-w-0 flex-1">
            <GraphSourceFocus compact={compactToolbar} isDark={isDark} projectId={selectedProject?.id ?? null} value={focusSourceId} disabled={isLoading} onChange={id => changeFocus(id, loadOverview)} />
          </div>
          {!compactToolbar && <>
            <button onClick={handleZoomIn} title={t('knowledgeGraphView.zoomIn')} aria-label={t('knowledgeGraphView.zoomIn')} className={cn('shrink-0 rounded-md p-1.5', iconBtn)}><ZoomIn className="h-3.5 w-3.5" /></button>
            <button onClick={handleZoomOut} title={t('knowledgeGraphView.zoomOut')} aria-label={t('knowledgeGraphView.zoomOut')} className={cn('shrink-0 rounded-md p-1.5', iconBtn)}><ZoomOut className="h-3.5 w-3.5" /></button>
          </>}
          <button onClick={() => graphRef.current?.zoomToFit(400, 40)} title={t('knowledgeGraphView.fitAllTitle')} aria-label={t('knowledgeGraphView.fitAllTitle')}
            className={cn('shrink-0 rounded-md p-1.5', iconBtn)}><Maximize2 className="h-3.5 w-3.5" /></button>
          <DropdownMenu modal={false} onOpenChange={open => { if (open) menuOpensPanelRef.current = false; }}>
            <DropdownMenuTrigger asChild>
              <button ref={viewTriggerRef} title={t('knowledgeGraphView.viewOptions')} aria-label={t('knowledgeGraphView.viewOptions')} className={cn('flex h-7 shrink-0 items-center gap-1 rounded-md border px-1.5 text-xs', chipBase)}>
                {compactToolbar ? <MoreHorizontal className="h-4 w-4" /> : <><Eye className="h-3.5 w-3.5" />{t('knowledgeGraphView.viewOptions')}</>}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" collisionPadding={8} onCloseAutoFocus={event => { if (menuOpensPanelRef.current) event.preventDefault(); }} className={cn('z-[100] max-h-[var(--radix-dropdown-menu-content-available-height)] max-w-[calc(100vw_-_1rem)] overflow-y-auto text-xs', isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-100' : 'bg-ds-white text-ds-zinc-900')}>
              <DropdownMenuItem onSelect={handleZoomIn}><ZoomIn className="mr-2 h-3.5 w-3.5" />{t('knowledgeGraphView.zoomIn')}</DropdownMenuItem>
              <DropdownMenuItem onSelect={handleZoomOut}><ZoomOut className="mr-2 h-3.5 w-3.5" />{t('knowledgeGraphView.zoomOut')}</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => loadOverview(true)} disabled={isLoading}><RefreshCw className={cn('mr-2 h-3.5 w-3.5', isLoading && 'animate-spin')} />{t('knowledgeGraphView.reloadTitle')}</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => { menuOpensPanelRef.current = toolSurface !== 'legend'; setToolSurface(current => current === 'legend' ? null : 'legend'); }}><Workflow className="mr-2 h-3.5 w-3.5" />{t('knowledgeGraphView.legendLabel')}</DropdownMenuItem>
              <DropdownMenuItem disabled={!panelOpen} onSelect={() => { menuOpensPanelRef.current = !showDetails; setToolSurface(null); setFocusDetails(!showDetails); setDetailsExpanded(!showDetails); }}><Info className="mr-2 h-3.5 w-3.5" />{t(showDetails ? 'knowledgeGraphView.hideDetails' : 'knowledgeGraphView.showDetails')}</DropdownMenuItem>
              <DropdownMenuItem disabled={!panelOpen} onSelect={clearGraphHighlight}><X className="mr-2 h-3.5 w-3.5" />{t('knowledgeGraphView.clearSelection')}</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        {viewMode === 'neighborhood' && (
          <div className="flex min-w-0 items-center gap-1 px-2 pb-1.5" data-testid="graph-neighborhood-navigation">
            <button onClick={handleBackToOverview} title={t('knowledgeGraphView.backToOverview')} aria-label={t('knowledgeGraphView.backToOverview')}
              className={cn('flex h-7 shrink-0 items-center gap-1 rounded border px-1.5 text-xs', chipBase)}>
              <ArrowLeft className="h-3.5 w-3.5" />{t('knowledgeGraphView.overviewShort')}
            </button>
            <span className={cn('min-w-0 flex-1 truncate text-xs', textMuted)} title={neighborhoodFocusNode?.label}>{neighborhoodFocusNode?.label}</span>
            {neighborhoodHasMore && <button onClick={loadMoreConnections} disabled={isLoadingMore} title={t('knowledgeGraphView.loadMoreConnectionsTitle')} aria-label={t('knowledgeGraphView.loadMoreConnections')}
              className={cn('flex h-7 shrink-0 items-center gap-1 rounded border px-1.5 text-xs disabled:opacity-50', chipBase)}>
              {isLoadingMore ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}{t('knowledgeGraphView.loadMoreShort')}
            </button>}
          </div>
        )}
        {(rawNodes.length > 0 || focusNodeId) && <div className={cn('flex min-w-0 items-center gap-2 px-2 pb-1 text-[0.625rem]', textMuted)}>
          <span className="min-w-0 truncate tabular-nums" title={t('knowledgeGraphView.graphCounts', { nodes: filteredData.nodes.length, links: filteredData.links.length })}>{t('knowledgeGraphView.graphCounts', { nodes: filteredData.nodes.length, links: filteredData.links.length })}</span>
          {agentGraphFocus && viewMode === 'neighborhood' && neighborhoodFocusNode?.id === agentGraphFocus.focus_id && <span className="min-w-0 flex-1 truncate" title={t('knowledgeGraphView.agentNeighborhoodScope', { focus: agentGraphFocus.focus_label, direction: agentDirectionLabel, relationships: agentRelationshipLabels ?? '', limit: neighborhoodLimit })}>
            {t('knowledgeGraphView.agentNeighborhoodScope', { focus: agentGraphFocus.focus_label, direction: agentDirectionLabel, relationships: agentRelationshipLabels ?? '', limit: neighborhoodLimit })}
          </span>}
          {(activeFocusNodeId || selectedEdgeId) && <button onClick={clearGraphHighlight} title={t('knowledgeGraphView.clearFocusTitle')} className="ml-auto shrink-0 text-ds-indigo-400 underline underline-offset-2">{t('knowledgeGraphView.clearFocus')}</button>}
        </div>}
      </div>

      {/* The canvas stays mounted while tools and inspectors change presentation. */}
      <div className={cn('relative flex flex-1 min-w-0 min-h-0', showDetails && detailMode === 'bottom' && 'flex-col')}>

        {/* Canvas */}
        <div ref={containerRef} className="flex-1 min-w-0 min-h-0 relative">
          {isLoading && (
            <div className={cn('absolute inset-0 z-20 flex items-center justify-center', isDark ? 'bg-ds-zinc-950/60' : 'bg-ds-white/65')}>
              <div className="flex w-[min(90%,26rem)] flex-col items-center gap-3 px-6 py-7 text-center">
                <p className={cn('text-sm font-medium', textMain)}>{t('knowledgeGraphView.loadingTitle')}</p>
                <p className={cn('max-w-md text-xs leading-relaxed', textMuted)}>{t('knowledgeGraphView.loadingDescription')}</p>
                <div className="h-1 w-56 overflow-hidden rounded-full bg-ds-indigo-500/15" role="progressbar" aria-label={t('knowledgeGraphView.loadingTitle')} aria-valuetext={t('knowledgeGraphView.loadingProgress')}>
                  <div className="h-full w-2/5 rounded-full bg-gradient-to-r from-ds-indigo-500/30 via-ds-indigo-400 to-ds-blue-400 animate-[loading-slide_1.6s_ease-in-out_infinite]" />
                </div>
                <p className={cn('text-[0.625rem]', textMuted)}>{t('knowledgeGraphView.loadingProgress')}</p>
              </div>
            </div>
          )}

          {!isLoading && rawNodes.length === 0 && (
            <div className={cn('absolute inset-0 flex flex-col items-center justify-center gap-2', textMuted)}>
              <BookOpen className="w-10 h-10 opacity-25" />
              <p className="text-sm">{t('knowledgeGraphView.noApprovedLinks')}</p>
              <p className="text-xs opacity-60">{t('knowledgeGraphView.noApprovedLinksHint')}</p>
            </div>
          )}

          {!isLoading && overviewTruncation && (
            <div className="absolute top-3 left-3 z-10 flex items-center gap-1.5 px-2 py-1 rounded border border-ds-amber-500/30 bg-ds-amber-500/10 text-[0.625rem] text-ds-amber-400 max-w-[min(90%,28rem)]">
              <AlertTriangle className="w-3 h-3 shrink-0" />
              {/* Bei gekürzten Beziehungen kennt die Übersicht nur die gelieferten Knoten, ein "n von n" wäre
                  irreführend: dann wird ausdrücklich eine Auswahl der Beziehungen gemeldet. */}
              <span>{overviewTruncation.edgesSampled && overviewTruncation.shown >= overviewTruncation.total
                ? t('knowledgeGraphView.truncatedEdgesNotice', { shown: overviewTruncation.shown })
                : t('knowledgeGraphView.truncatedOverviewNotice', { shown: overviewTruncation.shown, total: overviewTruncation.total })}</span>
            </div>
          )}

          {neighborhoodError && (
            <div className="absolute top-3 left-3 z-10 flex items-center gap-1.5 px-2 py-1 rounded border border-ds-red-500/30 bg-ds-red-500/10 text-[0.625rem] text-ds-red-400">
              <AlertTriangle className="w-3 h-3 shrink-0" />
              {neighborhoodError}
            </div>
          )}

          {!isLoading && activeFocusNodeId && focusNeighborIds && focusNeighborIds.size <= 1 && (
            <div className={cn('absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-3 py-1.5 rounded-sm border text-[0.6875rem]', chipBase, textMuted)}>
              <Info className="w-3 h-3" />
              {t('knowledgeGraphView.noLinkedObjectsFound')}
            </div>
          )}

          {ForceGraphComponent && !isLoading && dimensions.width > 0 && filteredData.nodes.length > 0 && (
            <ForceGraphComponent
              ref={graphRef}
              graphData={filteredData}
              width={dimensions.width}
              height={dimensions.height}
              backgroundColor={graphBg}
              nodeCanvasObject={renderer.drawNode}
              nodeVisibility={renderer.nodeVisible}
              linkVisibility={renderer.linkVisible}
              onRenderFramePre={updateViewport}
              nodeCanvasObjectMode={() => 'replace'}
              nodePointerAreaPaint={(node: GraphNode, color: string, ctx: CanvasRenderingContext2D) => {
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(node.x ?? 0, node.y ?? 0, renderer.hitRadius(node), 0, 2 * Math.PI);
                ctx.fill();
              }}
              linkColor={renderer.linkColor}
              linkWidth={renderer.linkWidth}
              onZoom={(transform: { k: number }) => { zoomRef.current = transform.k; }}
              linkDirectionalArrowLength={renderer.arrowLength}
              linkDirectionalArrowRelPos={renderer.arrowRelPos}
              linkCanvasObject={renderer.drawSourceArrow}
              linkCanvasObjectMode={() => 'after'}
              linkCurvature={renderer.curvature}
              autoPauseRedraw
              onNodeClick={(node: GraphNode) => {
                setSelectedNodeId(prev => prev === node.id ? null : node.id);
                setSelectedEdgeId(null);
                if (node.type === 'entity' || node.type === 'code_file') {
                  // Ein einfacher Klick stupst nur ein bereits offenes, nicht eingefrorenes
                  // Code-Panel an — er öffnet nie ein neues (openIfMissing=false).
                  // source_id muss mit, sonst kann page.tsx::handlePanelFileSelect die
                  // Entity nicht per api.resolveEntity() auflösen (Git-Quellen sind nicht
                  // "local", die Dateiname-Heuristik in resolveReferenceTarget() greift
                  // nicht) — der Editor bleibt dann leer, siehe SplitPaneWorkspace.tsx'
                  // Lade-Effekt, der ohne selectedEntity.source_id keinen der drei
                  // Content-Zweige treffen kann.
                  if (node.file_path && onFileSelect) {
                    onFileSelect(node.file_path, node.start_line || null, node.source_id ?? null, false);
                  }
                  if (node.type === 'entity' && onEntitySelect) {
                    onEntitySelect({
                      name: node.label,
                      type: node.entity_type,
                      id: extractEntityDbId(node.id) ?? undefined,
                      file_path: node.file_path || '',
                      start_line: node.start_line ?? 1,
                    });
                  }
                } else if (node.type === 'document' || node.type === 'external') {
                  const { pathVal, sourceIdVal } = resolveDocSelector(node);
                  // Wie im Entity-Zweig: nur anstupsen, nicht öffnen (openIfMissing=false).
                  // Ebenfalls genau ein Aufruf (O-091) -- der zweite Schreibweg
                  // über onDocFocus traf sonst auch hier ein offenes doc-Panel.
                  if (onFileSelect) onFileSelect(pathVal, null, sourceIdVal, false);
                }
              }}
              onNodeDragEnd={(node: GraphNode) => {
                // Force-graph releases fx/fy after a drag by default, so the
                // simulation pulls the node back into its previous layout.
                // Keep the user's chosen position fixed while other nodes settle.
                if (node.x != null) node.fx = node.x;
                if (node.y != null) node.fy = node.y;
              }}
              onLinkClick={(link: GraphEdge) => {
                // Eine Kante wählt nur sich selbst aus (zeigt die Edge-Detailkarte) und
                // öffnet KEINE Code-/Dokument-Ansicht — das war zuvor fälschlich an das
                // bevorzugte Endpunkt-Node der Kante gekoppelt.
                setSelectedEdgeId(prev => prev === link.id ? null : link.id);
                setSelectedNodeId(null);
              }}
              onBackgroundClick={clearGraphHighlight}
              cooldownTicks={0}
              enableNodeDrag
              enablePanInteraction
              enableZoomInteraction
            />
          )}

        </div>

        {showDetails && <GraphToolPanel title={selectionLabel} isDark={isDark} mode={detailMode} autoFocus={focusDetails}
          back={inspectorBack ? { label: t('knowledgeGraphView.backTo', { label: inspectorBackLabel }), onBack: goInspectorBack } : undefined}
          height={Math.min(320, Math.floor(panelSize.height * 0.42))} returnFocusRef={viewTriggerRef}
          onClose={() => {
            setDetailsExpanded(false);
            setFocusDetails(false);
            requestAnimationFrame(() => detailsTriggerRef.current?.focus());
          }}>
          {renderDetailContent()}
        </GraphToolPanel>}

        {toolSurface && <GraphToolPanel key={toolSurface} title={t(toolSurface === 'filters' ? 'knowledgeGraphView.filters' : 'knowledgeGraphView.legendLabel')}
          isDark={isDark} mode="tools" autoFocus returnFocusRef={toolSurface === 'filters' ? filterTriggerRef : viewTriggerRef} onClose={closeToolSurface}>
          <GraphFilterPanel isDark={isDark} legend={toolSurface === 'legend'}
            nodes={nodeTypes.flatMap(type => {
              const info = UNIFIED_NODE_TYPES[type];
              return info ? [{ id: type, label: language === 'de' ? info.labelDe : info.labelEn, hidden: hiddenNodeTypes.has(type) }] : [];
            })}
            links={linkTypes.map(type => ({ id: type, label: getLinkLabel(t, type) ?? type, hidden: hiddenLinkTypes.has(type), color: getGraphEdgeColor(type) }))}
            directions={edgeDirections.map(direction => ({ id: direction, label: t(EDGE_DIRECTION_TAXONOMY[direction].labelKey), hidden: hiddenEdgeDirections.has(direction) }))}
            onToggleNode={toggleNodeType} onToggleLink={toggleLinkType} onToggleDirection={id => toggleEdgeDirection(id as GraphEdgeDirection)}
            onReset={() => { setHiddenNodeTypes(new Set()); setHiddenLinkTypes(new Set()); setHiddenEdgeDirections(new Set()); }} />
        </GraphToolPanel>}
      </div>

      {panelOpen && !showDetails && <div className={cn('flex min-w-0 shrink-0 items-center gap-1 border-t px-2 py-1', border)}>
        <button ref={detailsTriggerRef} onClick={() => { setToolSurface(null); setFocusDetails(true); setDetailsExpanded(true); }} title={selectionLabel}
          aria-label={t('knowledgeGraphView.showDetails')} className="flex min-w-0 flex-1 items-center gap-2 rounded px-1 py-1 text-xs hover:bg-ds-zinc-500/10">
          <Info className="h-3.5 w-3.5 shrink-0 text-ds-indigo-400" /><span className="min-w-0 flex-1 truncate text-left">{selectionLabel}</span>
          <span className="shrink-0 text-ds-indigo-400">{t('knowledgeGraphView.details')}</span>
        </button>
        <button onClick={clearGraphHighlight} title={t('knowledgeGraphView.clearSelection')} aria-label={t('knowledgeGraphView.clearSelection')} className={cn('shrink-0 rounded p-1', iconBtn)}><X className="h-3.5 w-3.5" /></button>
      </div>}
    </div>
  );
}
