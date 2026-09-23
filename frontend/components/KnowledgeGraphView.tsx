"use client";
import type { CodeEntity, WorkspaceDocument } from '@/types/domain';
import type { ForceGraphMethods, ForceGraphProps } from 'react-force-graph-2d';

import { api, API_URL } from '@/app/services/api';
import {
  EDGE_TYPE_COLORS,
  NODE_TYPE_TAXONOMY,
  getEntityTypeLabel,
  EDGE_DIRECTION_TAXONOMY,
  getGraphEdgeColor,
  getGraphEdgeLabelKey,
  normalizeGraphEdgeDirection,
  getGraphNodeCategory,
  getGraphNodeColor,
  type GraphEdgeDirection,
} from '@/lib/graphTaxonomy';
import { resolveDsColor } from '@/lib/designTokens';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { forceCollide, forceManyBody } from 'd3-force-3d';
import { AlertTriangle, BookOpen, Check, ChevronDown, ChevronUp, Crosshair, ExternalLink, Info, LayoutGrid, Link2, Loader2, Maximize2, PanelRightClose, PanelRightOpen, Plus, RefreshCw, Search, Workflow, X, ZoomIn, ZoomOut } from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { drawKnowledgeNodeIcon, KnowledgeNodeIcon } from './KnowledgeNodeIcon';

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

// Shared by the canvas drawing and the collision force below so the physics
// always matches what's actually painted — a mismatch would leave nodes
// either overlapping (radius too small) or spaced needlessly far apart
// (radius too large).
function nodeRadius(node: GraphNode, degree = 0): number {
  const baseRadius = node?.type === 'entity' || node?.type === 'code_file' ? 8 : 7;
  return baseRadius + Math.min(9, Math.sqrt(degree) * 1.8);
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

export interface GraphNode {
  id: string;
  type: 'entity' | 'code_file' | 'document' | 'copybook' | 'external';
  label: string;
  entity_type?: string;
  language?: string;
  analysis_status?: 'partial' | 'text_fallback' | 'skipped' | 'error';
  analysis_reasons?: string[];
  file_path?: string;
  start_line?: number;
  source_type?: string;
  url?: string;
  project_id?: number;
  unresolved?: boolean;
  source_id?: number | string | null;
  entity_ids?: number[];
  resource_type?: string;
  resource_id?: string | number | null;
  x?: number;
  y?: number;
}

function getNodeDisplayLabel(node: GraphNode): string {
  if (node.type !== 'code_file' || !node.file_path) return node.label;
  return node.file_path.split(/[\\/]/).filter(Boolean).pop() || node.label;
}

export interface GraphEdge {
  id: string;
  source: string | GraphNode;
  target: string | GraphNode;
  link_type: string;
  /** Broad graph relationship family, e.g. `documented` for EntityDocLink. */
  relation_type?: string;
  /** O-264/O-265: Directionality of the relationship ('directed' | 'undirected' | 'bidirectional') */
  direction?: 'directed' | 'undirected' | 'bidirectional';
  score: number | null;
  context: string | null;
  /** Optional code-edge fields; relationship types remain open strings. */
  type?: string;
  resolution?: string | null;
  meta?: Record<string, unknown>;
  start_line?: number | null;
  end_line?: number | null;
  chunk_id?: number | null;
  document_file_path?: string | null;
  document_source_id?: number | string | null;
  document_start_line?: number | null;
  document_end_line?: number | null;
  document_page?: number | string | null;
  document_section?: string | null;
  document_url_anchor?: string | null;
  document_url?: string | null;
  code_file_path?: string | null;
  code_entity_id?: number | null;
  code_entity_name?: string | null;
  code_entity_type?: string | null;
  code_start_line?: number | null;
}

export function isEdgeDirected(edge: GraphEdge): boolean {
  const legacyFallback = edge.id.startsWith('code:') || edge.id.startsWith('edl:') || edge.id.startsWith('ref:')
    ? 'directed'
    : 'undirected';
  return EDGE_DIRECTION_TAXONOMY[normalizeGraphEdgeDirection(edge.direction, legacyFallback)].arrowheads > 0;
}

function graphEdgeDirection(edge: GraphEdge): GraphEdgeDirection {
  const legacyFallback = edge.id.startsWith('code:') || edge.id.startsWith('edl:') || edge.id.startsWith('ref:')
    ? 'directed'
    : 'undirected';
  return normalizeGraphEdgeDirection(edge.direction, legacyFallback);
}

function graphEdgeType(edge: Pick<GraphEdge, 'link_type' | 'relation_type'>): string {
  return edge.relation_type ?? edge.link_type;
}

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
  // How many panels are open in the surrounding workspace grid. With 3 or 4 panels
  // open at once there isn't room for a right-hand sidebar, so the detail panel
  // moves into a collapsible bottom drawer instead.
  layoutMode?: '1-pane' | 'split' | '3-col' | '4-grid';
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
  layoutMode
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
  const [overviewTruncation, setOverviewTruncation] = useState<{ shown: number; total: number } | null>(null);
  const [viewMode, setViewMode] = useState<'overview' | 'neighborhood'>('overview');
  const [neighborhoodError, setNeighborhoodError] = useState<string | null>(null);
  const [isLoadingNeighborhood, setIsLoadingNeighborhood] = useState(false);
  const [neighborhoodFocusNode, setNeighborhoodFocusNode] = useState<GraphNode | null>(null);
  const [neighborhoodCursor, setNeighborhoodCursor] = useState<string | null>(null);
  const [neighborhoodHasMore, setNeighborhoodHasMore] = useState<boolean>(false);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [traversalDirection, setTraversalDirection] = useState<'incoming' | 'outgoing' | 'both'>('both');
  const [traversalHops, setTraversalHops] = useState<1 | 2 | 3 | 4 | 5>(1);
  // The knowledge graph is a relationship view. Unlinked inventory belongs in
  // a paginated list, because rendering it here creates thousands of meaningless
  // force-layout nodes and obscures the actual code/document evidence network.
  const onlyLinked = true;

  // Keep the expensive initial overview alive while a node neighborhood is shown.
  // The neighborhood replaces the rendered data temporarily, but must not discard
  // the large overview which the user already waited for.
  const overviewCacheRef = useRef<{
    projectId: number | null;
    includeIsolated: boolean;
    nodes: GraphNode[];
    edges: GraphEdge[];
    truncation: { shown: number; total: number } | null;
  } | null>(null);

  // Manual link creation (connect the selected node to any other loaded node)
  const [isLinkPickerOpen, setIsLinkPickerOpen] = useState(false);
  const [linkPickerQuery, setLinkPickerQuery] = useState('');
  const [linkPickerTargetId, setLinkPickerTargetId] = useState<string | null>(null);
  const [manualLinkDirection, setManualLinkDirection] = useState<GraphEdgeDirection>('undirected');
  const [isCreatingLink, setIsCreatingLink] = useState(false);
  const [linkCreateError, setLinkCreateError] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
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
  const [isLegendOpen, setIsLegendOpen] = useState(true);

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

  const loadOverview = useCallback(async (force = false, includeIsolatedOverride?: boolean) => {
    /** Loads all approved links of the repository from the backend. */
    const projectId = selectedProject?.id ?? null;
    const includeIsolated = includeIsolatedOverride ?? !onlyLinked;
    const cachedOverview = overviewCacheRef.current;
    if (!force && cachedOverview?.projectId === projectId && cachedOverview?.includeIsolated === includeIsolated) {
      setRawNodes(cachedOverview.nodes);
      setRawEdges(cachedOverview.edges);
      setOverviewTruncation(cachedOverview.truncation);
      setViewMode('overview');
      setNeighborhoodFocusNode(null);
      setNeighborhoodCursor(null);
      setNeighborhoodHasMore(false);
      setIsLoadingMore(false);
      setNeighborhoodError(null);
      setSelectedEdgeId(null);
      setLinkFilterResetToken(previous => previous + 1);

      if (selectedDoc) {
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
      const res = await api.fetch(`${API_URL}/graph?${params}`);
      const data: { nodes?: GraphNode[]; edges?: GraphEdge[]; truncated?: boolean; total_nodes?: number; focus_id?: string } = await res.json();
      const nodes = data.nodes ?? [];
      const edges = data.edges ?? [];
      const truncation = data.truncated ? { shown: nodes.length, total: data.total_nodes ?? nodes.length } : null;
      overviewCacheRef.current = { projectId, includeIsolated, nodes, edges, truncation };
      setRawNodes(nodes);
      setRawEdges(edges);
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
      if (selectedDoc) {
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
  }, [selectedProject, selectedDoc, onlyLinked]);

  const neighborhoodProjectId = useCallback((node: GraphNode): number | null => {
    return node.project_id ?? selectedProject?.id ?? null;
  }, [selectedProject]);

  const loadNeighborhood = useCallback(async (node: GraphNode) => {
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
    if (!isDoc && !isFile && (entityDbId === null || projectId === null)) {
      setNeighborhoodError(t('knowledgeGraphView.loadNeighborhoodUnavailable'));
      return;
    }
    setIsLoadingNeighborhood(true);
    setNeighborhoodError(null);
    try {
      let res: Response;
      if (isDoc || isFile) {
        const params = new URLSearchParams({ node_id: node.id, status: 'approved' });
        if (projectId !== null) params.set('project_id', String(projectId));
        res = await api.fetch(`${API_URL}/graph/neighborhood?${params}`);
      } else {
        const params = new URLSearchParams({
          status: 'approved', project_id: String(projectId), entity_id: String(entityDbId),
          direction: traversalDirection, hops: String(traversalHops),
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
  }, [neighborhoodFocusNode, neighborhoodCursor, isLoadingMore, neighborhoodProjectId, t, traversalDirection, traversalHops]);

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
        context: null,
      }]);
      setIsLinkPickerOpen(false);
      setLinkPickerQuery('');
      setLinkPickerTargetId(null);
      setManualLinkDirection('undirected');
    } catch (e) {
      console.error('[KnowledgeGraph] manual link creation failed', e);
      setLinkCreateError(t('knowledgeGraphView.createLinkError'));
    } finally {
      setIsCreatingLink(false);
    }
  }, [t, manualLinkDirection]);

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

  // Overview-Graph laden — bleibt immer vollständig geladen, "Fokus" ist rein visuell.
  useEffect(() => {
    (async () => {
      await loadOverview();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProject?.id]);

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
  const filteredData = useMemo(() => {
    const candidateNodes = rawNodes.filter(n => !hiddenNodeTypes.has(nodeTypeKey(n)));
    const candidateIds = new Set(candidateNodes.map(n => n.id));
    const visibleEdges = rawEdges.filter(e => {
      const src = typeof e.source === 'object' ? (e.source as GraphNode).id : e.source;
      const tgt = typeof e.target === 'object' ? (e.target as GraphNode).id : e.target;
      return !hiddenLinkTypes.has(graphEdgeType(e))
        && !hiddenEdgeDirections.has(graphEdgeDirection(e))
        && candidateIds.has(src)
        && candidateIds.has(tgt);
    });

    let visibleNodes = candidateNodes;
    if (onlyLinked) {
      const connectedNodeIds = new Set<string>();
      for (const e of visibleEdges) {
        const src = typeof e.source === 'object' ? (e.source as GraphNode).id : e.source;
        const tgt = typeof e.target === 'object' ? (e.target as GraphNode).id : e.target;
        connectedNodeIds.add(src);
        connectedNodeIds.add(tgt);
      }
      visibleNodes = candidateNodes.filter(n => connectedNodeIds.has(n.id));
    }

    return { nodes: visibleNodes, links: visibleEdges };
  }, [rawNodes, rawEdges, hiddenNodeTypes, hiddenLinkTypes, hiddenEdgeDirections, onlyLinked]);

  const nodeDegrees = useMemo(() => {
    const degrees = new Map<string, number>();
    for (const edge of filteredData.links) {
      const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
      const targetId = typeof edge.target === 'object' ? edge.target.id : edge.target;
      degrees.set(sourceId, (degrees.get(sourceId) ?? 0) + 1);
      degrees.set(targetId, (degrees.get(targetId) ?? 0) + 1);
    }
    return degrees;
  }, [filteredData.links]);

  // Camera centering on node/edge selection
  useEffect(() => {
    if (!graphRef.current) return;

    if (selectedNodeId) {
      const node = rawNodes.find(n => n.id === selectedNodeId);
      if (node && node.x !== undefined && node.y !== undefined) {
        graphRef.current.centerAt(node.x, node.y, 800);
        graphRef.current.zoom(2.0, 800);
      } else {
        const timer = setTimeout(() => {
          if (!graphRef.current) return;
          const currentNodes = filteredData.nodes;
          const found = currentNodes.find((n: GraphNode) => n.id === selectedNodeId);
          if (found && found.x !== undefined && found.y !== undefined) {
            graphRef.current.centerAt(found.x, found.y, 800);
            graphRef.current.zoom(2.0, 800);
          }
        }, 300);
        return () => clearTimeout(timer);
      }
    } else if (selectedEdgeId) {
      const edge = rawEdges.find(e => e.id === selectedEdgeId);
      if (edge) {
        const srcId = typeof edge.source === 'object' ? edge.source.id : edge.source;
        const tgtId = typeof edge.target === 'object' ? edge.target.id : edge.target;

        const srcNode = rawNodes.find(n => n.id === srcId);
        const tgtNode = rawNodes.find(n => n.id === tgtId);

        if (srcNode && tgtNode && srcNode.x !== undefined && srcNode.y !== undefined && tgtNode.x !== undefined && tgtNode.y !== undefined) {
          const centerX = (srcNode.x + tgtNode.x) / 2;
          const centerY = (srcNode.y + tgtNode.y) / 2;
          graphRef.current.centerAt(centerX, centerY, 800);
          graphRef.current.zoom(2.0, 800);
        } else {
          const timer = setTimeout(() => {
            if (!graphRef.current) return;
            const currentNodes = filteredData.nodes;
            const currentEdges = filteredData.links;
            const foundEdge = currentEdges.find((e: GraphEdge) => e.id === selectedEdgeId);
            if (foundEdge) {
              const sId = typeof foundEdge.source === 'object' ? foundEdge.source.id : foundEdge.source;
              const tId = typeof foundEdge.target === 'object' ? foundEdge.target.id : foundEdge.target;
              const sNode = currentNodes.find((n: GraphNode) => n.id === sId);
              const tNode = currentNodes.find((n: GraphNode) => n.id === tId);
              if (sNode && tNode && sNode.x !== undefined && sNode.y !== undefined && tNode.x !== undefined && tNode.y !== undefined) {
                const centerX = (sNode.x + tNode.x) / 2;
                const centerY = (sNode.y + tNode.y) / 2;
                graphRef.current.centerAt(centerX, centerY, 800);
                graphRef.current.zoom(2.0, 800);
              }
            }
          }, 300);
          return () => clearTimeout(timer);
        }
      }
    }
  }, [selectedNodeId, selectedEdgeId, rawNodes, rawEdges, filteredData]);

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

  // Tune the force simulation whenever the visible node/link set changes. The
  // library's defaults (charge -30, no collision force) are tuned for small
  // demo graphs — on a real project graph they let nodes sit on top of each
  // other and let edges cut straight through unrelated nodes. This does three
  // things instead:
  //  1. A collision force keeps node circles (+ a margin for their label) from
  //     ever overlapping, however dense the graph gets.
  //  2. Charge (repulsion) scales up with node count, so large graphs actually
  //     spread out instead of collapsing into a dense, unreadable clump.
  //  3. A longer link (rest) distance gives edges more room to route around
  //     third-party nodes rather than passing straight through them.
  // None of this is a hard geometric guarantee against an edge ever crossing a
  // node — it's a physics simulation, not a constraint solver — but it makes
  // both failure modes rare even on graphs with hundreds of nodes.
  useEffect(() => {
    if (!graphRef.current) return;
    const nodeCount = filteredData.nodes.length;
    if (nodeCount === 0) return;

    graphRef.current.d3Force('collide', forceCollide((n: GraphNode) => {
      const degree = nodeDegrees.get(n.id) ?? 0;
      return nodeRadius(n, degree) + 16 + Math.sqrt(degree) * 2;
    }).iterations(3));

    const chargeStrength = -Math.min(260, 40 + nodeCount * 0.6);
    graphRef.current.d3Force('charge', forceManyBody()
      .strength((n: unknown) => {
        const degree = nodeDegrees.get((n as GraphNode).id) ?? 0;
        return chargeStrength - Math.min(180, degree * 8);
      })
      .distanceMax(900));

    const linkForce = graphRef.current.d3Force('link');
    if (linkForce) {
      linkForce.distance((edge: GraphEdge) => {
        const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
        const targetId = typeof edge.target === 'object' ? edge.target.id : edge.target;
        const endpointDegrees = Math.sqrt(nodeDegrees.get(sourceId) ?? 0) + Math.sqrt(nodeDegrees.get(targetId) ?? 0);
        return 65 + Math.min(55, endpointDegrees * 5);
      }).strength(0.25);
    }

    // O-270: a bounded directional neighborhood is easier to read as layers
    // than as a force-directed cloud.  Cycles are harmless here: BFS assigns
    // the first observed layer and never revisits a node.
    if (viewMode === 'neighborhood' && neighborhoodFocusNode) {
      const rootId = neighborhoodFocusNode.id;
      const layers = new Map<string, number>([[rootId, 0]]);
      const pending = [rootId];
      while (pending.length) {
        const current = pending.shift()!;
        const layer = layers.get(current)!;
        for (const edge of filteredData.links) {
          const source = typeof edge.source === 'object' ? edge.source.id : edge.source;
          const target = typeof edge.target === 'object' ? edge.target.id : edge.target;
          const directed = isEdgeDirected(edge);
          const next: string[] = [];
          if (!directed || traversalDirection === 'both') {
            if (source === current) next.push(target);
            if (target === current) next.push(source);
          } else if (traversalDirection === 'outgoing' && source === current) {
            next.push(target);
          } else if (traversalDirection === 'incoming' && target === current) {
            next.push(source);
          }
          for (const nodeId of next) {
            if (!layers.has(nodeId)) {
              layers.set(nodeId, layer + 1);
              pending.push(nodeId);
            }
          }
        }
      }
      const perLayer = new Map<number, number>();
      const positions = new Map<string, { x: number; y: number }>();
      for (const node of [...filteredData.nodes].sort((a, b) => a.id.localeCompare(b.id))) {
        const layer = layers.get(node.id) ?? 0;
        const index = perLayer.get(layer) ?? 0;
        perLayer.set(layer, index + 1);
        const x = traversalDirection === 'incoming' ? -layer * 130 : layer * 130;
        positions.set(node.id, { x, y: index * 70 });
      }
      for (const node of filteredData.nodes) {
        const position = positions.get(node.id);
        if (!position) continue;
        // react-force-graph forwards these D3 coordinates to the simulation.
        // Pinning only the bounded traversal keeps its layers stable while the
        // overview remains freely explorable.
        Object.assign(node, { fx: position.x, fy: position.y });
      }
    }

    graphRef.current.d3ReheatSimulation();
  }, [ForceGraphComponent, filteredData, nodeDegrees, viewMode, neighborhoodFocusNode, traversalDirection]);

  // Nodes directly connected to focusNodeId (incl. itself) — everything else dims.
  // Clicking an edge produces the same soft-focus effect for just its two endpoints,
  // as long as no explicit node focus is active (that takes priority — it has its
  // own toolbar indicator/"clear focus" affordance and shouldn't get silently
  // swapped out by an incidental edge click). selectedEdgeId already resets to null
  // on any node click and switches to the new id on any other edge click (see
  // onNodeClick/onLinkClick below), so this normalizes on its own without extra state.
  const focusNeighborIds = useMemo(() => {
    if (focusNodeId) {
      const ids = new Set<string>([focusNodeId]);
      filteredData.links.forEach((l: GraphEdge) => {
        const src = typeof l.source === 'object' ? l.source.id : l.source;
        const tgt = typeof l.target === 'object' ? l.target.id : l.target;
        if (src === focusNodeId) ids.add(tgt);
        if (tgt === focusNodeId) ids.add(src);
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
  }, [focusNodeId, selectedEdgeId, filteredData]);

  // Only links touching focusNodeId itself stay colored — a link between two of its
  // neighbors (but not the focus node) still dims, matching the dimmed-node set above.
  // For an edge-driven soft focus, only that single edge stays colored.
  const isLinkTouchingFocus = useCallback((l: GraphEdge) => {
    if (focusNodeId) {
      const src = typeof l.source === 'object' ? l.source.id : l.source;
      const tgt = typeof l.target === 'object' ? l.target.id : l.target;
      return src === focusNodeId || tgt === focusNodeId;
    }
    if (selectedEdgeId) return l.id === selectedEdgeId;
    return true;
  }, [focusNodeId, selectedEdgeId]);

  const selectedNode = useMemo(() => rawNodes.find(n => n.id === selectedNodeId) ?? null, [rawNodes, selectedNodeId]);
  const selectedEdge = useMemo(() => rawEdges.find(e => e.id === selectedEdgeId) ?? null, [rawEdges, selectedEdgeId]);

  // O-266: Pair mapping to compute linkCurvature for opposing or parallel edges between the same two nodes
  const edgePairMap = useMemo(() => {
    const map = new Map<string, GraphEdge[]>();
    filteredData.links.forEach((l: GraphEdge) => {
      const s = typeof l.source === 'object' ? (l.source as GraphNode).id : l.source;
      const t = typeof l.target === 'object' ? (l.target as GraphNode).id : l.target;
      if (!s || !t) return;
      const key = s < t ? `${s}--${t}` : `${t}--${s}`;
      const list = map.get(key) || [];
      list.push(l);
      map.set(key, list);
    });
    return map;
  }, [filteredData.links]);

  const getLinkCurvature = useCallback((l: GraphEdge) => {
    const s = typeof l.source === 'object' ? (l.source as GraphNode).id : l.source;
    const t = typeof l.target === 'object' ? (l.target as GraphNode).id : l.target;
    if (!s || !t) return 0;
    const key = s < t ? `${s}--${t}` : `${t}--${s}`;
    const pairList = edgePairMap.get(key);
    if (!pairList || pairList.length <= 1) {
      return l.id.startsWith('kl:') ? 0.08 : 0;
    }
    const idx = pairList.findIndex(e => e.id === l.id);
    if (pairList.length === 2) {
      const [e1, e2] = pairList;
      const s1 = typeof e1.source === 'object' ? (e1.source as GraphNode).id : e1.source;
      const s2 = typeof e2.source === 'object' ? (e2.source as GraphNode).id : e2.source;
      // If opposing directions (A->B and B->A), both curve positively relative to their direction,
      // which curves them away from each other on canvas.
      if (s1 !== s2) {
        return 0.2;
      }
      return idx === 0 ? 0.2 : -0.2;
    }
    const offset = ((idx - (pairList.length - 1) / 2) / (pairList.length - 1)) * 0.4;
    return offset || 0.05;
  }, [edgePairMap]);

  const getLinkArrowLength = useCallback((l: GraphEdge) => {
    if (!isEdgeDirected(l)) return 0;
    return l.id === selectedEdgeId ? 6.5 : 4;
  }, [selectedEdgeId]);

  const getLinkArrowRelPos = useCallback((l: GraphEdge) => {
    if (!isEdgeDirected(l)) return 0.5;
    const targetNode = typeof l.target === 'object' && l.target !== null ? (l.target as GraphNode) : null;
    const sourceNode = typeof l.source === 'object' && l.source !== null ? (l.source as GraphNode) : null;
    if (targetNode && sourceNode && targetNode.x != null && targetNode.y != null && sourceNode.x != null && sourceNode.y != null) {
      const dx = targetNode.x - sourceNode.x;
      const dy = targetNode.y - sourceNode.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist > 0) {
    const r = nodeRadius(targetNode, nodeDegrees.get(targetNode.id) ?? 0);
        const targetOffset = (r + 1) / dist;
        return Math.max(0.1, Math.min(0.95, 1 - targetOffset));
      }
    }
    return 0.88;
  }, [nodeDegrees]);

  const drawBidirectionalSourceArrow = useCallback((edge: GraphEdge, ctx: CanvasRenderingContext2D) => {
    if (graphEdgeDirection(edge) !== 'bidirectional') return;
    const source = resolveNode(edge.source);
    const target = resolveNode(edge.target);
    if (!source || !target || source.x == null || source.y == null || target.x == null || target.y == null) return;

    const dx = source.x - target.x;
    const dy = source.y - target.y;
    const distance = Math.hypot(dx, dy);
    if (distance === 0) return;

    const ux = dx / distance;
    const uy = dy / distance;
    const px = -uy;
    const py = ux;
    const tipDistance = nodeRadius(source, nodeDegrees.get(source.id) ?? 0) + 1;
    const tipX = source.x + ux * tipDistance;
    const tipY = source.y + uy * tipDistance;
    const arrowLength = 5;
    const halfWidth = 2;
    const baseX = tipX - ux * arrowLength;
    const baseY = tipY - uy * arrowLength;

    ctx.save();
    ctx.fillStyle = edge.id === selectedEdgeId
      ? (isDark ? '#38bdf8' : '#0284c7')
      : resolveDsColor(getGraphEdgeColor(graphEdgeType(edge)));
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(baseX + px * halfWidth, baseY + py * halfWidth);
    ctx.lineTo(baseX - px * halfWidth, baseY - py * halfWidth);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }, [isDark, selectedEdgeId, rawNodes, nodeDegrees]);

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
  const drawNode = useCallback((node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const r = nodeRadius(node, nodeDegrees.get(node.id) ?? 0);
    const isSelected = node.id === selectedNodeId;
    const isFocus = node.id === focusNodeId;
    const isPrimary = isSelected || isFocus;
    const isDimmed = focusNeighborIds != null && !focusNeighborIds.has(node.id);
    const color = resolveDsColor(nodeColor(node));

    ctx.save();
    ctx.globalAlpha = isDimmed ? 0.15 : 1;

    const now = performance.now();

    if (isPrimary) {
      // 1. Radar pulse
      const pulseProgress = (now % 1200) / 1200;
      const pulseR = r + (pulseProgress * 12) / globalScale;
      const pulseAlpha = (1 - pulseProgress) * (isDark ? 0.75 : 0.55);
      ctx.beginPath();
      ctx.arc(node.x ?? 0, node.y ?? 0, pulseR, 0, 2 * Math.PI);
      ctx.strokeStyle = isDark
        ? `rgba(56, 189, 248, ${pulseAlpha})`
        : `rgba(2, 132, 199, ${pulseAlpha})`;
      ctx.lineWidth = 2 / globalScale;
      ctx.stroke();

      // 2. High-contrast guide track (provides contrast on white canvas!)
      const trackR = r + 2.8 / globalScale;
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
    }

    ctx.beginPath();
    ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
    drawKnowledgeNodeIcon(node, ctx, globalScale);

    if (isPrimary) {
      ctx.strokeStyle = isDark ? '#38bdf8' : '#ffffff';
      ctx.lineWidth = 2 / globalScale;
      ctx.stroke();
    }

    if (globalScale > 0.45) {
      const label = getNodeDisplayLabel(node) ?? '';
      const fontSize = Math.min(11, 8 / globalScale * 1.8);
      ctx.font = `${isPrimary ? 'bold ' : ''}${fontSize}px Inter, system-ui, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillStyle = isPrimary
        ? (isDark ? '#f8fafc' : '#0f172a')
        : resolveDsColor(isDark ? 'rgb(var(--ds-neutral-200))' : 'rgb(var(--ds-neutral-600))');
      ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + r + 3 / globalScale);
    }
    ctx.restore();
  }, [selectedNodeId, focusNodeId, isDark, focusNeighborIds, nodeDegrees]);

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
  const PANEL_W = 260;

  // With 3 or 4 panels open at once there's no room for a right-hand sidebar, so
  // the detail panel becomes a collapsible bottom drawer instead. With only 1-2
  // panels open there's room to spare, so the sidebar itself can be collapsed
  // on demand via the toolbar toggle.
  const isCompactLayout = layoutMode === '3-col' || layoutMode === '4-grid';
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isBottomDrawerExpanded, setIsBottomDrawerExpanded] = useState(false);

  // Require an explicit expand on every new selection rather than staying open
  // from the previous one. During render, same reasoning as the focus/selection
  // syncs above.
  const [prevSelectionForDrawer, setPrevSelectionForDrawer] = useState({ selectedNodeId, selectedEdgeId });
  if (prevSelectionForDrawer.selectedNodeId !== selectedNodeId || prevSelectionForDrawer.selectedEdgeId !== selectedEdgeId) {
    setPrevSelectionForDrawer({ selectedNodeId, selectedEdgeId });
    setIsBottomDrawerExpanded(false);
  }

  const showSidebar = panelOpen && !isCompactLayout && !isSidebarCollapsed;
  const showBottomDrawer = panelOpen && isCompactLayout;

  /* ── Theme tokens ───────────────────────────────────────────────────────────── */
  const border     = isDark ? 'border-ds-zinc-800'             : 'border-ds-zinc-200';
  const textMain   = isDark ? 'text-ds-zinc-100'               : 'text-ds-zinc-900';
  const textMuted  = isDark ? 'text-ds-zinc-500'               : 'text-ds-zinc-400';
  const panelBg    = isDark ? 'bg-ds-zinc-900 border-ds-zinc-800' : 'bg-ds-white border-ds-zinc-200';
  const chipBase   = isDark ? 'border-ds-zinc-700 hover:border-ds-zinc-500' : 'border-ds-zinc-300 hover:border-ds-zinc-400';
  const iconBtn    = isDark ? 'text-ds-zinc-500 hover:text-ds-zinc-200 hover:bg-ds-zinc-800' : 'text-ds-zinc-400 hover:text-ds-zinc-700 hover:bg-ds-zinc-100';
  const badge      = isDark ? 'bg-ds-zinc-800 text-ds-zinc-400'  : 'bg-ds-zinc-100 text-ds-zinc-500';
  const connRow    = isDark ? 'hover:bg-ds-zinc-800/60'        : 'hover:bg-ds-zinc-50';
  const graphBg    = resolveDsColor(isDark ? 'rgb(var(--ds-neutral-800))' : 'rgb(var(--ds-neutral-100))');

  /* ── Helpers for detail panel ───────────────────────────────────────────────── */
  function resolveNode(ref: string | GraphNode | null | undefined): GraphNode | undefined {
    if (!ref) return undefined;
    if (typeof ref === 'object') return ref as GraphNode;
    return rawNodes.find(n => n.id === ref);
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

  // Shared between the sidebar overlay (spacious layouts) and the bottom drawer
  // (compact 3-/4-panel layouts) — only the surrounding container differs.
  // showNodeName is false in the bottom drawer, whose own collapsible header already
  // shows selectedNode.label — repeating it here would print the name twice.
  const renderDetailContent = (showNodeName: boolean) => (
    <>
      {/* Node detail */}
      {selectedNode && (
        <div className="min-w-0 px-3 py-3 space-y-4 flex-1">
          {showNodeName && (
            <div className="flex items-start gap-2">
              <KnowledgeNodeIcon node={selectedNode} className="w-3.5 h-3.5 mt-0.5 shrink-0 text-ds-indigo-400" />
              <p className={cn('text-xs font-semibold leading-snug break-words', textMain)}>
                {getNodeDisplayLabel(selectedNode)}
              </p>
            </div>
          )}

          <div className="space-y-2">
            {selectedNode.entity_type && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[10px] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.typeLabel')}</span>
                <span className={cn('text-[10px] px-1.5 py-0.5 rounded', badge)}>
                  {getEntityTypeLabel(selectedNode.entity_type, language)}
                </span>
              </div>
            )}
            {selectedNode.language && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[10px] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.languageLabel')}</span>
                <span className={cn('text-[10px] px-1.5 py-0.5 rounded', badge)}>{selectedNode.language}</span>
              </div>
            )}
            {selectedNode.analysis_status && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[10px] w-14 shrink-0', textMuted)}>{t('provenance.analysisStatusLabel')}</span>
                <span
                  className={cn('text-[10px] px-1.5 py-0.5 rounded', badge)}
                  title={selectedNode.analysis_reasons?.join('; ')}
                >
                  {t(`analysisStatus.${selectedNode.analysis_status}`)}
                </span>
              </div>
            )}
            {selectedNode.file_path && (selectedNode.type === 'entity' || selectedNode.type === 'code_file') && (
              selectedNode.type === 'code_file' ? (
                <div className="flex min-w-0 items-baseline gap-2">
                  <span className={cn('text-[10px] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.fileLabel')}</span>
                  <span
                    className={cn('min-w-0 flex-1 truncate text-[10px] font-mono leading-snug', textMain)}
                    title={selectedNode.file_path}
                  >
                    {selectedNode.file_path}
                  </span>
                </div>
              ) : (
                <div className="flex items-baseline gap-2">
                  <span className={cn('text-[10px] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.fileLabel')}</span>
                  <span className={cn('text-[10px] font-mono break-all leading-snug', textMain)}>
                    {selectedNode.file_path}{selectedNode.start_line ? `:${selectedNode.start_line}` : ''}
                  </span>
                </div>
              )
            )}
            {selectedNode.source_type && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[10px] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.sourceLabel')}</span>
                <span className={cn('text-[10px] px-1.5 py-0.5 rounded', badge)}>
                  {selectedNode.source_type}
                </span>
              </div>
            )}
            {selectedNode.resource_type && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[10px] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.resourceLabel')}</span>
                <span className={cn('text-[10px] px-1.5 py-0.5 rounded', badge)}>
                  {t(`knowledgeGraphView.resourceTypes.${selectedNode.resource_type}`)}
                </span>
              </div>
            )}
            {selectedNode.type === 'external' && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[10px] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.statusLabel')}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-ds-zinc-500/15 text-ds-zinc-400 border border-ds-zinc-500/25">
                  {t('knowledgeGraphView.notFoundInProject')}
                </span>
              </div>
            )}
          </div>

          {/* Connected nodes */}
          <div className={cn('pt-3 border-t', border)}>
            <p className={cn('text-[10px] font-medium mb-2', textMuted)}>{t('knowledgeGraphView.connectionsLabel')}</p>
            <div className="space-y-0.5">
              {filteredData.links
                .filter((l: GraphEdge) => {
                  const s = typeof l.source === 'object' ? l.source.id : l.source;
                  const t = typeof l.target === 'object' ? l.target.id : l.target;
                  return s === selectedNode.id || t === selectedNode.id;
                })
                .slice(0, 10)
                .map((l: GraphEdge, i: number) => {
                  const src = resolveNode(l.source);
                  const tgt = resolveNode(l.target);
                  const other = src?.id === selectedNode.id ? tgt : src;
                  if (!other) return null;
                  return (
                    <button key={i}
                      onClick={() => { setSelectedNodeId(other.id); setSelectedEdgeId(null); }}
                      className={cn('w-full text-left flex items-center gap-2 px-1.5 py-1 rounded text-[10px] transition-colors', connRow)}>
                      <span className="w-3 shrink-0" style={{ height: 2, background: getGraphEdgeColor(graphEdgeType(l)), display: 'inline-block', borderRadius: 1 }} />
                      <span className={cn('truncate', textMain)}>{other.label}</span>
                    </button>
                  );
                })}
            </div>
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
                className="flex items-center gap-1.5 text-[11px] text-ds-indigo-400 hover:text-ds-indigo-300 transition-colors">
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
                className="flex items-center gap-1.5 text-[11px] text-ds-indigo-400 hover:text-ds-indigo-300 transition-colors">
                <ExternalLink className="w-3 h-3" />
                {t('knowledgeGraphView.openInView')}
              </button>
            )}

            {selectedNode.id !== focusNodeId && (
              <button
                onClick={() => setFocusNodeId(selectedNode.id)}
                className="flex items-center gap-1.5 text-[11px] text-ds-indigo-400 hover:text-ds-indigo-300 transition-colors">
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
                      className={cn('rounded border px-1 py-0.5 text-[10px]', chipBase, isDark ? 'bg-ds-zinc-900' : 'bg-ds-white')}>
                      <option value="incoming">{t('knowledgeGraphView.traversalIncoming')}</option>
                      <option value="outgoing">{t('knowledgeGraphView.traversalOutgoing')}</option>
                      <option value="both">{t('knowledgeGraphView.traversalBoth')}</option>
                    </select>
                    <select
                      value={traversalHops}
                      onChange={event => setTraversalHops(Number(event.target.value) as 1 | 2 | 3 | 4 | 5)}
                      aria-label={t('knowledgeGraphView.traversalHopsLabel')}
                      className={cn('rounded border px-1 py-0.5 text-[10px]', chipBase, isDark ? 'bg-ds-zinc-900' : 'bg-ds-white')}>
                      {[1, 2, 3, 4, 5].map(hop => <option key={hop} value={hop}>{t('knowledgeGraphView.traversalHops', { count: hop })}</option>)}
                    </select>
                  </>
                )}
                <button
                  onClick={() => loadNeighborhood(selectedNode)}
                  disabled={isLoadingNeighborhood}
                  title={t('knowledgeGraphView.loadNeighborhoodTitle')}
                  className={cn('flex items-center gap-1.5 text-[11px] transition-colors',
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
                className={cn('flex items-center gap-1.5 text-[11px] transition-colors',
                  isLoadingMore ? 'opacity-50 cursor-not-allowed text-ds-indigo-400' : 'text-ds-indigo-400 hover:text-ds-indigo-300')}>
                {isLoadingMore ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
                {t('knowledgeGraphView.loadMoreConnections')}
              </button>
            )}

            <button
              disabled={selectedNode.type === 'code_file' && !selectedNode.entity_ids?.length}
              onClick={() => { setIsLinkPickerOpen(o => !o); setLinkCreateError(null); }}
              className={cn('flex items-center gap-1.5 text-[11px] transition-colors',
                selectedNode.type === 'code_file' && !selectedNode.entity_ids?.length
                  ? 'opacity-40 cursor-not-allowed text-ds-zinc-500'
                  : 'text-ds-indigo-400 hover:text-ds-indigo-300')}>
              <Link2 className="w-3 h-3" />
              {t('knowledgeGraphView.createLink')}
            </button>

            {isLinkPickerOpen && (
              <div className={cn('p-2 rounded border space-y-2', border, isDark ? 'bg-ds-zinc-800/60' : 'bg-ds-zinc-50')}>
                <div className="flex items-center gap-1.5">
                  <Search className="w-3 h-3 shrink-0 text-ds-zinc-500" />
                  <input
                    autoFocus
                    value={linkPickerQuery}
                    onChange={e => { setLinkPickerQuery(e.target.value); setLinkPickerTargetId(null); }}
                    placeholder={t('knowledgeGraphView.createLinkTargetPlaceholder')}
                    className={cn('w-full bg-transparent text-[11px] outline-none', textMain)}
                  />
                </div>
                <div className="max-h-32 overflow-y-auto space-y-0.5">
                  {linkPickerCandidates.map(n => (
                    <button key={n.id}
                      onClick={() => setLinkPickerTargetId(n.id)}
                      className={cn('w-full text-left flex items-center gap-2 px-1.5 py-1 rounded text-[10px] transition-colors',
                        linkPickerTargetId === n.id ? (isDark ? 'bg-ds-indigo-500/20' : 'bg-ds-indigo-100') : connRow)}>
                      <KnowledgeNodeIcon node={n} className="w-3 h-3 shrink-0 text-ds-indigo-400" />
                      <span className={cn('truncate', textMain)}>{n.label}</span>
                      {linkPickerTargetId === n.id && <Check className="w-3 h-3 shrink-0 text-ds-indigo-400 ml-auto" />}
                    </button>
                  ))}
                  {linkPickerCandidates.length === 0 && (
                    <p className={cn('text-[10px] px-1.5 py-1', textMuted)}>{t('knowledgeGraphView.createLinkNoMatches')}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <label htmlFor="manual-link-direction" className={cn('text-[10px] shrink-0', textMuted)}>
                    {t('knowledgeGraphView.createLinkDirectionLabel')}
                  </label>
                  <select
                    id="manual-link-direction"
                    value={manualLinkDirection}
                    onChange={event => setManualLinkDirection(event.target.value as GraphEdgeDirection)}
                    className={cn('min-w-0 flex-1 rounded border px-1.5 py-1 text-[10px]', chipBase, isDark ? 'bg-ds-zinc-900 text-ds-zinc-200' : 'bg-ds-white text-ds-zinc-700')}>
                    <option value="undirected">{t(EDGE_DIRECTION_TAXONOMY.undirected.labelKey)}</option>
                    <option value="directed">{t(EDGE_DIRECTION_TAXONOMY.directed.labelKey)}</option>
                    <option value="bidirectional">{t(EDGE_DIRECTION_TAXONOMY.bidirectional.labelKey)}</option>
                  </select>
                </div>
                {linkCreateError && <p className="text-[10px] text-ds-red-400">{linkCreateError}</p>}
                <div className="flex items-center gap-2 justify-end">
                  <button onClick={() => { setIsLinkPickerOpen(false); setLinkPickerTargetId(null); setLinkCreateError(null); }}
                    className={cn('text-[10px] px-2 py-1 rounded transition-colors', textMuted, 'hover:text-ds-zinc-200')}>
                    {t('knowledgeGraphView.createLinkCancel')}
                  </button>
                  <button
                    disabled={!linkPickerTargetId || isCreatingLink}
                    onClick={() => {
                      const target = rawNodes.find(n => n.id === linkPickerTargetId);
                      if (target) createManualLink(selectedNode, target);
                    }}
                    className={cn('text-[10px] px-2 py-1 rounded font-medium transition-colors',
                      !linkPickerTargetId || isCreatingLink ? 'opacity-40 cursor-not-allowed bg-ds-indigo-500/40 text-ds-white' : 'bg-ds-indigo-500 hover:bg-ds-indigo-400 text-ds-white')}>
                    {isCreatingLink ? t('knowledgeGraphView.createLinkSaving') : t('knowledgeGraphView.createLinkConfirm')}
                  </button>
                </div>
              </div>
            )}

            {selectedNode.url && (
              <a href={selectedNode.url} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-[11px] text-ds-indigo-400 hover:text-ds-indigo-300 transition-colors">
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
            <span className={cn('text-[10px] px-1.5 py-0.5 rounded', badge)}>
              {getLinkLabel(t, graphEdgeType(selectedEdge)) ?? graphEdgeType(selectedEdge)}
            </span>
            <span className={cn('text-[10px] px-1.5 py-0.5 rounded', badge)}>
              {t(EDGE_DIRECTION_TAXONOMY[graphEdgeDirection(selectedEdge)].labelKey)}
            </span>
            {selectedEdge.score !== null && (
              <span className="text-[10px] font-mono text-ds-emerald-500">
                {Math.round((selectedEdge.score ?? 0) * 100)}%
              </span>
            )}
          </div>

          {edgeSrc && (
            <div>
              <p className={cn('text-[10px] mb-1', textMuted)}>{t('knowledgeGraphView.fromLabel')}</p>
              <button onClick={() => { setSelectedNodeId(edgeSrc.id); setSelectedEdgeId(null); }}
                className={cn('w-full text-left flex items-center gap-2 px-1.5 py-1 rounded text-xs transition-colors', connRow)}>
                <KnowledgeNodeIcon node={edgeSrc} className="w-3 h-3 shrink-0 text-ds-indigo-400" />
                <span className={cn('min-w-0 font-medium truncate', textMain)}>{getNodeDisplayLabel(edgeSrc)}</span>
              </button>
            </div>
          )}

          {edgeTgt && (
            <div>
              <p className={cn('text-[10px] mb-1', textMuted)}>{t('knowledgeGraphView.toLabel')}</p>
              <button onClick={() => { setSelectedNodeId(edgeTgt.id); setSelectedEdgeId(null); }}
                className={cn('w-full text-left flex items-center gap-2 px-1.5 py-1 rounded text-xs transition-colors', connRow)}>
                <KnowledgeNodeIcon node={edgeTgt} className="w-3 h-3 shrink-0 text-ds-indigo-400" />
                <span className={cn('min-w-0 font-medium truncate', textMain)}>{getNodeDisplayLabel(edgeTgt)}</span>
              </button>
            </div>
          )}

          {selectedEdge.context && (
            <div className={cn('box-border min-w-0 w-full max-w-full whitespace-pre-wrap break-words [overflow-wrap:anywhere] p-2 rounded text-[10px] leading-relaxed', isDark ? 'bg-ds-zinc-800 text-ds-zinc-300' : 'bg-ds-zinc-50 text-ds-zinc-600')}>
              {selectedEdge.context}
            </div>
          )}

          {selectedEdgeLocation && (
            <div className="space-y-1">
              <p className={cn('text-[10px]', textMuted)}>{t('knowledgeGraphView.documentLocationLabel')}</p>
              <p className={cn('text-[10px] font-mono break-words', textMain)}>{selectedEdgeLocation}</p>
            </div>
          )}

          {selectedEdge.code_file_path && edgeTgt && onFileSelect && (
            <button
              onClick={() => onFileSelect(
                selectedEdge.code_file_path!,
                selectedEdge.code_start_line ?? null,
                edgeTgt.source_id ?? null,
              )}
              className="flex items-center gap-1.5 text-[11px] text-ds-indigo-400 hover:text-ds-indigo-300 transition-colors">
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
              className="flex items-center gap-1.5 text-[11px] text-ds-indigo-400 hover:text-ds-indigo-300 transition-colors">
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
    <div className="flex flex-col h-full min-h-0">

      {/* ── Filter toolbar ── */}
      <div className={cn('flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2 border-b shrink-0', border)}>

        {/* Node type chips */}
        {nodeTypes.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className={cn('text-[10px] uppercase tracking-wider font-medium', textMuted)}>{t('knowledgeGraphView.nodesLabel')}</span>
            {nodeTypes.map(type => {
              const typeInfo = UNIFIED_NODE_TYPES[type];
              if (!typeInfo) return null;
              const label = language === 'de' ? typeInfo.labelDe : typeInfo.labelEn;
              const hidden = hiddenNodeTypes.has(type);
              return (
                <button key={type} onClick={() => toggleNodeType(type)}
                  className={cn('flex items-center gap-1.5 px-2 py-0.5 rounded-sm border text-[10px] transition-all', chipBase,
                    hidden ? 'opacity-30' : 'opacity-100')}>
                  <KnowledgeNodeIcon node={{ type, source_type: type }} className="w-3 h-3 shrink-0 text-ds-indigo-400" />
                  {label}
                </button>
              );
            })}
          </div>
        )}

        {nodeTypes.length > 0 && linkTypes.length > 0 && (
          <div className={cn('h-4 w-px shrink-0', border)} />
        )}

        {/* Link type chips */}
        {linkTypes.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className={cn('text-[10px] uppercase tracking-wider font-medium', textMuted)}>{t('knowledgeGraphView.linksLabel')}</span>
            {linkTypes.map(type => {
              const color = getGraphEdgeColor(type);
              const hidden = hiddenLinkTypes.has(type);
              return (
                <button key={type} onClick={() => toggleLinkType(type)}
                  className={cn('flex items-center gap-1.5 px-2 py-0.5 rounded-sm border text-[10px] transition-all', chipBase,
                    hidden ? 'opacity-30' : 'opacity-100')}>
                  <span className="w-4 rounded-sm shrink-0" style={{ background: color, height: 2 }} />
                  {getLinkLabel(t, type) ?? type}
                </button>
              );
            })}
          </div>
        )}

        {linkTypes.length > 0 && edgeDirections.length > 0 && (
          <div className={cn('h-4 w-px shrink-0', border)} />
        )}

        {/* Direction filter for the currently focused graph data */}
        {edgeDirections.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className={cn('text-[10px] uppercase tracking-wider font-medium', textMuted)}>
              {t('knowledgeGraphView.directionFilterLabel')}
            </span>
            {edgeDirections.map(direction => {
              const hidden = hiddenEdgeDirections.has(direction);
              return (
                <button key={direction} onClick={() => toggleEdgeDirection(direction)}
                  aria-pressed={!hidden}
                  className={cn('flex items-center gap-1.5 px-2 py-0.5 rounded-sm border text-[10px] transition-all', chipBase,
                    hidden ? 'opacity-30' : 'opacity-100')}>
                  {t(EDGE_DIRECTION_TAXONOMY[direction].labelKey)}
                </button>
              );
            })}
          </div>
        )}

        {/* Right: focus indicator + counts + controls */}
        <div className="ml-auto flex items-center gap-1.5 shrink-0">
          {viewMode === 'neighborhood' && (
            <>
              <button onClick={() => loadOverview()} title={t('knowledgeGraphView.backToOverview')}
                className={cn('flex items-center gap-1.5 px-2 py-1 rounded-md border text-[10px] transition-colors', chipBase, textMuted)}>
                <LayoutGrid className="w-3 h-3" />
                {t('knowledgeGraphView.backToOverview')}
              </button>
              {neighborhoodHasMore && (
                <button
                  onClick={loadMoreConnections}
                  disabled={isLoadingMore}
                  title={t('knowledgeGraphView.loadMoreConnectionsTitle')}
                  className={cn('flex items-center gap-1.5 px-2 py-1 rounded-md border text-[10px] transition-colors', chipBase, textMuted,
                    isLoadingMore && 'opacity-50 cursor-not-allowed')}>
                  {isLoadingMore ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
                  {t('knowledgeGraphView.loadMoreConnections')}
                </button>
              )}
            </>
          )}
          {focusNodeId && (
            <button onClick={() => setFocusNodeId(null)} title={t('knowledgeGraphView.clearFocusTitle')}
              className={cn('flex items-center gap-1.5 px-2 py-1 rounded-md border text-[10px] transition-colors', chipBase, textMuted)}>
              <LayoutGrid className="w-3 h-3" />
              {t('knowledgeGraphView.clearFocus')}
            </button>
          )}
          {rawNodes.length > 0 && (
            <span className={cn('text-[10px] tabular-nums', textMuted)}>
              {filteredData.nodes.length} · {filteredData.links.length}
            </span>
          )}
          <button onClick={handleZoomIn} title={t('knowledgeGraphView.zoomIn')}
            className={cn('p-1.5 rounded-md transition-colors', iconBtn)}>
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button onClick={handleZoomOut} title={t('knowledgeGraphView.zoomOut')}
            className={cn('p-1.5 rounded-md transition-colors', iconBtn)}>
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button onClick={() => graphRef.current?.zoomToFit(400, 40)} title={t('knowledgeGraphView.fitAllTitle')}
            className={cn('p-1.5 rounded-md transition-colors', iconBtn)}>
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
          <button onClick={() => loadOverview(true)}
            disabled={isLoading} title={t('knowledgeGraphView.reloadTitle')}
            className={cn('p-1.5 rounded-md transition-colors', iconBtn)}>
            <RefreshCw className={cn('w-3.5 h-3.5', isLoading && 'animate-spin')} />
          </button>
          {!isCompactLayout && (
            <button onClick={() => setIsSidebarCollapsed(c => !c)}
              title={t(isSidebarCollapsed ? 'knowledgeGraphView.expandSidebarTitle' : 'knowledgeGraphView.collapseSidebarTitle')}
              className={cn('p-1.5 rounded-md transition-colors', iconBtn)}>
              {isSidebarCollapsed ? <PanelRightOpen className="w-3.5 h-3.5" /> : <PanelRightClose className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>
      </div>

      {/* ── Graph canvas + detail panel ── */}
      <div className="relative flex flex-1 min-w-0 min-h-0">

        {/* Canvas */}
        <div ref={containerRef} className="flex-1 min-w-0 min-h-0 relative">
          {isLoading && (
            <div className={cn('absolute inset-0 z-20 flex items-center justify-center', isDark ? 'bg-ds-zinc-950/60' : 'bg-white/65')}>
              <div className="flex w-[min(90%,26rem)] flex-col items-center gap-3 px-6 py-7 text-center">
                <p className={cn('text-sm font-medium', textMain)}>{t('knowledgeGraphView.loadingTitle')}</p>
                <p className={cn('max-w-md text-xs leading-relaxed', textMuted)}>{t('knowledgeGraphView.loadingDescription')}</p>
                <div className="h-1 w-56 overflow-hidden rounded-full bg-ds-indigo-500/15" role="progressbar" aria-label={t('knowledgeGraphView.loadingTitle')} aria-valuetext={t('knowledgeGraphView.loadingProgress')}>
                  <div className="h-full w-2/5 rounded-full bg-gradient-to-r from-ds-indigo-500/30 via-ds-indigo-400 to-ds-blue-400 animate-[loading-slide_1.6s_ease-in-out_infinite]" />
                </div>
                <p className={cn('text-[10px]', textMuted)}>{t('knowledgeGraphView.loadingProgress')}</p>
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
            <div className="absolute top-3 left-3 z-10 flex items-center gap-1.5 px-2 py-1 rounded border border-ds-amber-500/30 bg-ds-amber-500/10 text-[10px] text-ds-amber-400 max-w-[min(90%,28rem)]">
              <AlertTriangle className="w-3 h-3 shrink-0" />
              <span>{t('knowledgeGraphView.truncatedOverviewNotice', { shown: overviewTruncation.shown, total: overviewTruncation.total })}</span>
            </div>
          )}

          {neighborhoodError && (
            <div className="absolute top-3 left-3 z-10 flex items-center gap-1.5 px-2 py-1 rounded border border-ds-red-500/30 bg-ds-red-500/10 text-[10px] text-ds-red-400">
              <AlertTriangle className="w-3 h-3 shrink-0" />
              {neighborhoodError}
            </div>
          )}

          {!isLoading && focusNodeId && focusNeighborIds && focusNeighborIds.size <= 1 && (
            <div className={cn('absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-3 py-1.5 rounded-sm border text-[11px]', chipBase, textMuted)}>
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
              nodeCanvasObject={drawNode}
              nodeCanvasObjectMode={() => 'replace'}
              nodePointerAreaPaint={(node: GraphNode, color: string, ctx: CanvasRenderingContext2D) => {
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(node.x ?? 0, node.y ?? 0, nodeRadius(node, nodeDegrees.get(node.id) ?? 0) + 4, 0, 2 * Math.PI);
                ctx.fill();
              }}
              linkColor={(l: GraphEdge) => {
                if (l.id === selectedEdgeId) {
                  return isDark ? '#38bdf8' : '#0284c7';
                }
                if (!isLinkTouchingFocus(l)) return isDark ? 'rgba(161,161,170,0.06)' : 'rgba(161,161,170,0.12)';
                return resolveDsColor(getGraphEdgeColor(graphEdgeType(l)));
              }}
              linkWidth={(l: GraphEdge) => l.id === selectedEdgeId ? 4.5 : Math.max(1.2, (l.score ?? 0.5) * 3)}
              linkDirectionalArrowLength={getLinkArrowLength}
              linkDirectionalArrowRelPos={getLinkArrowRelPos}
              linkCanvasObject={drawBidirectionalSourceArrow}
              linkCanvasObjectMode={() => 'after'}
              linkCurvature={getLinkCurvature}
              linkDirectionalParticles={(l: GraphEdge) => l.id === selectedEdgeId ? 3 : 0}
              linkDirectionalParticleSpeed={(l: GraphEdge) => l.id === selectedEdgeId ? 0.012 : 0.005}
              linkDirectionalParticleWidth={(l: GraphEdge) => l.id === selectedEdgeId ? 5 : 2.5}
              linkDirectionalParticleCanvasObject={(x: number, y: number, l: GraphEdge, ctx: CanvasRenderingContext2D, globalScale: number) => {
                const isSelected = l.id === selectedEdgeId;
                const pR = (isSelected ? 3.5 : 2) / globalScale;
                ctx.save();
                ctx.beginPath();
                ctx.arc(x, y, pR, 0, 2 * Math.PI);
                if (!isDark) {
                  ctx.fillStyle = '#ffffff';
                  ctx.shadowColor = 'rgba(0, 0, 0, 0.65)';
                  ctx.shadowBlur = 3;
                  ctx.fill();
                  ctx.lineWidth = 1.2 / globalScale;
                  ctx.strokeStyle = isSelected ? '#0284c7' : '#64748b';
                  ctx.stroke();
                } else {
                  ctx.fillStyle = '#ffffff';
                  ctx.shadowColor = isSelected ? '#38bdf8' : '#94a3b8';
                  ctx.shadowBlur = isSelected ? 8 : 4;
                  ctx.fill();
                }
                ctx.restore();
              }}
              autoPauseRedraw={!selectedNodeId && !focusNodeId}
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
              onLinkClick={(link: GraphEdge) => {
                // Eine Kante wählt nur sich selbst aus (zeigt die Edge-Detailkarte) und
                // öffnet KEINE Code-/Dokument-Ansicht — das war zuvor fälschlich an das
                // bevorzugte Endpunkt-Node der Kante gekoppelt.
                setSelectedEdgeId(prev => prev === link.id ? null : link.id);
                setSelectedNodeId(null);
              }}
              onBackgroundClick={() => { setSelectedNodeId(null); setSelectedEdgeId(null); }}
              d3AlphaDecay={0.02}
              d3VelocityDecay={0.3}
              cooldownTime={3000}
              enableNodeDrag
              enablePanInteraction
              enableZoomInteraction
            />
          )}

          {/* Floating Legend */}
          {filteredData.nodes.length > 0 && (
            <div className={cn(
              "absolute left-4 z-20 rounded-lg border p-3 shadow-lg transition-all backdrop-blur-md max-w-[220px] select-none",
              // Bei kompaktem Layout (3/4 Panels offen) liegt der Detail-Bottom-Drawer
              // unten im Canvas, auch expandiert bis zu 60% Höhe — eine bottom-*-Position
              // der Legende kann ihm dann nie zuverlässig ausweichen. Deshalb bei
              // isCompactLayout fix oben links statt unten links, unabhängig davon, ob der
              // Drawer gerade sichtbar/expandiert ist (kein Springen beim Auswählen/Schließen).
              isCompactLayout ? "top-4" : "bottom-4",
              isDark ? "bg-ds-zinc-900/85 border-ds-zinc-800 text-ds-zinc-200" : "bg-ds-white/85 border-ds-zinc-200 text-ds-zinc-800"
            )}>
              <div className="flex items-center justify-between gap-4 cursor-pointer" onClick={() => setIsLegendOpen(o => !o)}>
                <div className="flex items-center gap-1.5">
                  <Workflow className="w-3.5 h-3.5 text-ds-indigo-500 animate-pulse" />
                  <span className="text-xs font-bold uppercase tracking-wide">
                    {t('knowledgeGraphView.legendLabel')}
                  </span>
                </div>
                <span className="text-[10px] text-ds-zinc-550 hover:text-ds-zinc-300">
                  {isLegendOpen ? '▲' : '▼'}
                </span>
              </div>

              {isLegendOpen && (
                <div className="mt-2.5 space-y-2.5 max-h-[220px] overflow-y-auto pr-1">
                  {/* List visible node types */}
                  <div className="space-y-1.5">
                    <p className="text-[9px] uppercase tracking-wider text-ds-zinc-500 font-semibold">
                      {t('knowledgeGraphView.nodesLabel')}
                    </p>
                    {nodeTypes.map(type => {
                      const typeInfo = UNIFIED_NODE_TYPES[type];
                      if (!typeInfo) return null;
                      const label = language === 'de' ? typeInfo.labelDe : typeInfo.labelEn;
                      return (
                        <div key={type} className="flex items-center gap-2 text-[10px]">
                          <KnowledgeNodeIcon node={{ type, source_type: type }} className="w-3 h-3 shrink-0 text-ds-indigo-400" />
                          <span className="truncate">{label}</span>
                        </div>
                      );
                    })}
                  </div>

                  {/* List visible link types */}
                  {linkTypes.length > 0 && (
                    <div className={cn("space-y-1.5 pt-2 border-t", isDark ? "border-ds-zinc-800/60" : "border-ds-zinc-200")}>
                      <p className="text-[9px] uppercase tracking-wider text-ds-zinc-500 font-semibold">
                        {t('knowledgeGraphView.linksLabel')}
                      </p>
                      {linkTypes.map(type => {
                        const color = getGraphEdgeColor(type);
                        const label = getLinkLabel(t, type) ?? type;
                        return (
                          <div key={type} className="flex items-center gap-2 text-[10px]">
                            <span className="w-4 rounded-sm shrink-0" style={{ background: color, height: 2 }} />
                            <span className="truncate">{label}</span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Detail sidebar (spacious layouts: 1 or 2 panels open) ── */}
        {showSidebar && (
          <div className={cn('absolute right-0 top-0 bottom-0 border-l overflow-y-auto z-30 flex flex-col shadow-2xl backdrop-blur-md', isDark ? 'bg-ds-zinc-900/95 border-ds-zinc-800' : 'bg-ds-white/95 border-ds-zinc-200')}
            style={{ width: PANEL_W }}>

            <div className={cn('flex items-center justify-between px-3 py-2 border-b shrink-0', border)}>
              <span className={cn('text-xs font-semibold', textMain)}>
                {selectedNode
                  ? (selectedNode.type === 'code_file' ? t('knowledgeGraphView.fileLabel') : selectedNode.type === 'entity' ? t('knowledgeGraphView.codeEntityLabel') : t('knowledgeGraphView.documentLabel'))
                  : t('knowledgeGraphView.linkLabel')}
              </span>
              <button onClick={() => { setSelectedNodeId(null); setSelectedEdgeId(null); }}
                className={cn('p-1 rounded transition-colors', iconBtn)}>
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            {renderDetailContent(true)}
          </div>
        )}

        {/* ── Detail bottom drawer (compact layouts: 3 or 4 panels open) — collapsed
            by default on every new selection, must be expanded to see details, so
            the graph keeps the full pane height in cramped grids. ── */}
        {showBottomDrawer && (
          <div className={cn('absolute left-0 right-0 bottom-0 border-t z-30 flex flex-col shadow-2xl backdrop-blur-md', isDark ? 'bg-ds-zinc-900/95 border-ds-zinc-800' : 'bg-ds-white/95 border-ds-zinc-200')}
            style={{ maxHeight: isBottomDrawerExpanded ? '60%' : undefined }}>

            <div className={cn('flex items-center gap-2 px-3 py-2 shrink-0 cursor-pointer', isBottomDrawerExpanded && 'border-b', border)}
              onClick={() => setIsBottomDrawerExpanded(o => !o)}>
              {selectedNode && (
                <KnowledgeNodeIcon node={selectedNode} className="w-3 h-3 shrink-0 text-ds-indigo-400" />
              )}
              {selectedEdge && !selectedNode && (
                <span className="w-4 shrink-0" style={{ height: 2, background: getGraphEdgeColor(graphEdgeType(selectedEdge)), display: 'inline-block', borderRadius: 1 }} />
              )}
              <span className={cn('text-xs font-semibold truncate flex-1', textMain)}>
                {selectedNode ? getNodeDisplayLabel(selectedNode) : (selectedEdge ? (getLinkLabel(t, graphEdgeType(selectedEdge)) ?? graphEdgeType(selectedEdge)) : '')}
              </span>
              <button onClick={(e) => { e.stopPropagation(); setSelectedNodeId(null); setSelectedEdgeId(null); }}
                className={cn('p-1 rounded transition-colors shrink-0', iconBtn)}>
                <X className="w-3.5 h-3.5" />
              </button>
              {isBottomDrawerExpanded ? <ChevronDown className="w-3.5 h-3.5 shrink-0" /> : <ChevronUp className="w-3.5 h-3.5 shrink-0" />}
            </div>

            {isBottomDrawerExpanded && (
              <div className="overflow-y-auto">
                {renderDetailContent(false)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
