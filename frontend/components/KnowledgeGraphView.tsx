"use client";

import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Loader2, ZoomIn, ZoomOut, Maximize2, RefreshCw, X, ExternalLink, BookOpen, LayoutGrid, Info, Workflow, Link2, Search, Check, PanelRightClose, PanelRightOpen, ChevronUp, ChevronDown } from 'lucide-react';
import { forceCollide, forceManyBody } from 'd3-force-3d';
import { cn } from '@/lib/utils';
import { resolveDsColor } from '@/lib/designTokens';
import { API_URL } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';

// ForceGraph2D will be loaded dynamically on mount

/* ── Color maps ──────────────────────────────────────────────────────────────── */

export const UNIFIED_NODE_TYPES: Record<string, { labelDe: string; labelEn: string; color: string }> = {
  cobol:      { labelDe: 'COBOL-Programme (.cbl/.cob)', labelEn: 'COBOL Programs (.cbl/.cob)', color: 'rgb(var(--ds-info-base))' }, // Blue
  pdf:        { labelDe: 'PDF-Dokumente (.pdf)', labelEn: 'PDF Documents (.pdf)', color: 'rgb(var(--ds-danger-base))' }, // Red
  jcl:        { labelDe: 'JCL (.jcl/.proc)', labelEn: 'JCL (.jcl/.proc)', color: 'rgb(var(--ds-warning-base))' }, // Orange
  confluence: { labelDe: 'Confluence', labelEn: 'Confluence', color: 'rgb(var(--ds-info-base))' }, // Cyan
  jira:       { labelDe: 'Jira Software', labelEn: 'Jira Software', color: 'rgb(var(--ds-accent))' }, // Indigo
  git:        { labelDe: 'Git / Code-Elemente', labelEn: 'Git / Code Elements', color: 'rgb(var(--ds-success-base))' }, // Green
  txt:        { labelDe: 'Text-Dateien (.txt)', labelEn: 'Text Files (.txt)', color: 'rgb(var(--ds-neutral-500))' }, // Slate
  md:         { labelDe: 'Markdown-Dateien (.md)', labelEn: 'Markdown Files (.md)', color: 'rgb(var(--ds-neutral-500))' }, // Gray
  copybook:   { labelDe: 'Copybook', labelEn: 'Copybook', color: 'rgb(var(--ds-graph-a-base))' }, // Violet
  external:   { labelDe: 'Externe Referenzen', labelEn: 'External References', color: 'rgb(var(--ds-neutral-500))' }, // Gray
  document:   { labelDe: 'Sonstige Dokumente', labelEn: 'Other Documents', color: 'rgb(var(--ds-neutral-300))' }, // Light Gray
};

export function getNodeType(node: any): string {
  if (!node) return 'document';

  // 1. Code entities
  if (node.type === 'entity') return 'git';
  if (node.type === 'copybook') return 'copybook';
  if (node.type === 'external') return 'external';

  // 2. For document nodes, check source type first
  const source = node.source_type || '';
  if (source === 'Confluence') return 'confluence';
  if (source === 'Jira') return 'jira';
  if (source === 'Git') return 'git';

  // 4. File extension checks on label/url/file_path
  const path = (node.file_path || node.url || node.label || '').toLowerCase();
  if (path.endsWith('.cbl') || path.endsWith('.cob') || path.endsWith('.cobol')) return 'cobol';
  if (path.endsWith('.cpy') || path.endsWith('.copy')) return 'copybook';
  if (path.endsWith('.jcl') || path.endsWith('.proc') || path.endsWith('.prc')) return 'jcl';
  if (path.endsWith('.pdf')) return 'pdf';
  if (path.endsWith('.txt')) return 'txt';
  if (path.endsWith('.md')) return 'md';

  return 'document';
}

export function nodeColor(node: any): string {
  const type = getNodeType(node);
  return UNIFIED_NODE_TYPES[type]?.color ?? 'rgb(var(--ds-neutral-300))';
}

function nodeTypeKey(node: any): string {
  return getNodeType(node);
}

// Shared by the canvas drawing and the collision force below so the physics
// always matches what's actually painted — a mismatch would leave nodes
// either overlapping (radius too small) or spaced needlessly far apart
// (radius too large).
function nodeRadius(node: any): number {
  return node?.type === 'entity' ? 7 : 6;
}

export const LINK_COLORS: Record<string, string> = {
  semantic:  'rgb(var(--ds-accent))',
  keyword:   'rgb(var(--ds-warning-base))',
  syntactic: 'rgb(var(--ds-success-base))',
  coref:     'rgb(var(--ds-graph-b-base))',
  manual:    'rgb(var(--ds-warning-base))',
  chat:      'rgb(var(--ds-info-base))',
  call:      'rgb(var(--ds-danger-base))',
  perform:   'rgb(var(--ds-success-base))',
  goto:      'rgb(var(--ds-warning-base))',
  copy:      'rgb(var(--ds-graph-a-base))',
  use:       'rgb(var(--ds-info-base))',
};

const LINK_LABEL_KEYS: Record<string, string> = {
  semantic:  'graphLabels.linkTypes.semantic',
  keyword:   'graphLabels.linkTypes.keyword',
  syntactic: 'graphLabels.linkTypes.syntactic',
  coref:     'graphLabels.linkTypes.coref',
  manual:    'graphLabels.linkTypes.manual',
  chat:      'graphLabels.linkTypes.chat',
  call:      'graphLabels.linkTypes.call',
  perform:   'graphLabels.linkTypes.perform',
  goto:      'graphLabels.linkTypes.goto',
  copy:      'graphLabels.linkTypes.copy',
  use:       'graphLabels.linkTypes.use',
};

export function getLinkLabel(t: (key: string) => string, type: string): string | undefined {
  const key = LINK_LABEL_KEYS[type];
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

interface GraphNode {
  id: string;
  type: 'entity' | 'document' | 'copybook' | 'external';
  label: string;
  entity_type?: string;
  file_path?: string;
  start_line?: number;
  source_type?: string;
  url?: string;
  project_id?: number;
  unresolved?: boolean;
  source_id?: number | string | null;
  x?: number;
  y?: number;
}

interface GraphEdge {
  id: string;
  source: string | GraphNode;
  target: string | GraphNode;
  link_type: string;
  score: number | null;
  context: string | null;
}

interface Props {
  theme: string;
  selectedProject: { id: number; name: string } | null;
  selectedEntity?: any | null;
  selectedFile?: string | null;
  selectedDoc?: any | null;
  projectEntities?: any[];
  onEntitySelect?: (ent: any) => Promise<void> | void;
  onFileSelect?: (path: string, line?: number | null, sourceId?: number | string | null, openIfMissing?: boolean) => Promise<void> | void;
  // Opens (or navigates an already-open) document panel for a plain document/PDF node.
  onDocFocus?: (filePath: string, sourceId: number | string | null, openIfMissing?: boolean) => void;
  // How many panels are open in the surrounding workspace grid. With 3 or 4 panels
  // open at once there isn't room for a right-hand sidebar, so the detail panel
  // moves into a collapsible bottom drawer instead.
  layoutMode?: '1-pane' | 'split' | '3-col' | '4-grid';
}

/* ── Component ───────────────────────────────────────────────────────────────── */

export function KnowledgeGraphView({
  theme,
  selectedProject,
  selectedEntity,
  selectedFile,
  selectedDoc,
  projectEntities = [],
  onEntitySelect,
  onFileSelect,
  onDocFocus,
  layoutMode
}: Props) {
  const { t, language } = useLanguage();
  const isDark = theme === 'dark';

  const [rawNodes, setRawNodes] = useState<GraphNode[]>([]);
  const [rawEdges, setRawEdges] = useState<GraphEdge[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  // Purely visual "soft focus": the full graph stays loaded, connected nodes/edges
  // just render at full opacity while everything else is dimmed. No separate backend
  // fetch/reload — the overview graph already carries every entity-doc and
  // entity-entity link, so there's nothing a restricted dataset would add.
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);

  // Manual link creation (connect the selected node to any other loaded node)
  const [isLinkPickerOpen, setIsLinkPickerOpen] = useState(false);
  const [linkPickerQuery, setLinkPickerQuery] = useState('');
  const [linkPickerTargetId, setLinkPickerTargetId] = useState<string | null>(null);
  const [isCreatingLink, setIsCreatingLink] = useState(false);
  const [linkCreateError, setLinkCreateError] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const graphRef = useRef<any>(null);

  const [ForceGraphComponent, setForceGraphComponent] = useState<any>(null);

  useEffect(() => {
    import('react-force-graph-2d').then((mod) => {
      setForceGraphComponent(() => mod.default);
    });
  }, []);

  const [hiddenNodeTypes, setHiddenNodeTypes] = useState<Set<string>>(new Set());
  const [hiddenLinkTypes, setHiddenLinkTypes] = useState<Set<string>>(new Set());
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

  const loadOverview = useCallback(async () => {
    /** Loads all approved links of the repository from the backend. */
    setIsLoading(true);
    try {
      const params = new URLSearchParams({ status: 'approved' });
      if (selectedProject?.id) params.set('project_id', String(selectedProject.id));
      const res = await fetch(`${API_URL}/graph?${params}`, { credentials: 'include' });
      const data = await res.json();
      const nodes = data.nodes ?? [];
      setRawNodes(nodes);
      setRawEdges(data.edges ?? []);

      // Auto-select document node if active
      if (selectedDoc) {
        const docNode = nodes.find((n: any) => n.id === `doc:${selectedDoc.url}` || n.label === selectedDoc.name);
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
  }, [selectedProject, selectedDoc]);

  const createManualLink = useCallback(async (sourceNode: GraphNode, targetNode: GraphNode) => {
    /** Connects two currently-loaded nodes via a manual KnowledgeLink (see backend/api/knowledge_links.py). */
    if (!sourceNode || !targetNode || sourceNode.id === targetNode.id) return;
    const sideFromNode = (n: GraphNode) => {
      if (n.type === 'entity') {
        const numId = parseInt(n.id.slice('entity:'.length), 10);
        return { type: 'entity', entity_id: Number.isNaN(numId) ? null : numId, title: n.label, url: n.url ?? null, source_type: n.entity_type ?? null };
      }
      return { type: 'document', entity_id: null, title: n.label, url: n.url ?? null, source_type: n.source_type ?? null };
    };
    const a = sideFromNode(sourceNode);
    const b = sideFromNode(targetNode);
    setIsCreatingLink(true);
    setLinkCreateError(null);
    try {
      const res = await fetch(`${API_URL}/knowledge-links`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_a_type: a.type, source_a_entity_id: a.entity_id, source_a_title: a.title, source_a_url: a.url, source_a_source_type: a.source_type,
          source_b_type: b.type, source_b_entity_id: b.entity_id, source_b_title: b.title, source_b_url: b.url, source_b_source_type: b.source_type,
          link_type: 'manual', status: 'approved',
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRawEdges(prev => [...prev, {
        id: `kl:${data.id}`,
        source: sourceNode.id,
        target: targetNode.id,
        link_type: 'manual',
        score: null,
        context: null,
      }]);
      setIsLinkPickerOpen(false);
      setLinkPickerQuery('');
      setLinkPickerTargetId(null);
    } catch (e) {
      console.error('[KnowledgeGraph] manual link creation failed', e);
      setLinkCreateError(t('knowledgeGraphView.createLinkError'));
    } finally {
      setIsCreatingLink(false);
    }
  }, [t]);

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
      const entId = extractEntityDbId(selectedEntity.id);
      if (entId != null) {
        setSelectedNodeId(`entity:${entId}`);
      }
    } else if (selectedDoc) {
      const docNode = rawNodes.find((n: any) => n.id === `doc:${selectedDoc.url}` || n.label === selectedDoc.name);
      if (docNode) setSelectedNodeId(docNode.id);
    } else if (selectedFile) {
      const fileNode = rawNodes.find((n: any) => n.id === `doc:${selectedFile}` || n.label === selectedFile || n.url === selectedFile);
      if (fileNode) {
        setSelectedNodeId(fileNode.id);
      } else {
        const entNode = rawNodes.find((n: any) => n.type === 'entity' && n.file_path === selectedFile);
        if (entNode) setSelectedNodeId(entNode.id);
      }
    }
  }

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
          const currentNodes = graphRef.current.graphData().nodes;
          const found = currentNodes.find((n: any) => n.id === selectedNodeId);
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
        const srcId = typeof edge.source === 'object' ? (edge.source as any).id : edge.source;
        const tgtId = typeof edge.target === 'object' ? (edge.target as any).id : edge.target;

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
            const currentNodes = graphRef.current.graphData().nodes;
            const currentEdges = graphRef.current.graphData().links;
            const foundEdge = currentEdges.find((e: any) => e.id === selectedEdgeId);
            if (foundEdge) {
              const sId = typeof foundEdge.source === 'object' ? foundEdge.source.id : foundEdge.source;
              const tId = typeof foundEdge.target === 'object' ? foundEdge.target.id : foundEdge.target;
              const sNode = currentNodes.find((n: any) => n.id === sId);
              const tNode = currentNodes.find((n: any) => n.id === tId);
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
  }, [selectedNodeId, selectedEdgeId, rawNodes, rawEdges]);

  // Available node/link types for filter chips
  const nodeTypes = useMemo(() => {
    const s = new Set<string>();
    rawNodes.forEach(n => s.add(nodeTypeKey(n)));
    return Array.from(s);
  }, [rawNodes]);

  const linkTypes = useMemo(() => {
    const s = new Set<string>();
    rawEdges.forEach(e => s.add(e.link_type));
    return Array.from(s);
  }, [rawEdges]);

  // Filtered data for the graph
  const filteredData = useMemo(() => {
    const visibleNodes = rawNodes.filter(n => !hiddenNodeTypes.has(nodeTypeKey(n)));
    const visibleIds = new Set(visibleNodes.map(n => n.id));
    const visibleEdges = rawEdges.filter(e => {
      const src = typeof e.source === 'object' ? (e.source as GraphNode).id : e.source;
      const tgt = typeof e.target === 'object' ? (e.target as GraphNode).id : e.target;
      return !hiddenLinkTypes.has(e.link_type) && visibleIds.has(src) && visibleIds.has(tgt);
    });
    return { nodes: visibleNodes, links: visibleEdges };
  }, [rawNodes, rawEdges, hiddenNodeTypes, hiddenLinkTypes]);

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

    graphRef.current.d3Force('collide', forceCollide((n: any) => nodeRadius(n) + 10).iterations(2));

    const chargeStrength = -Math.min(260, 40 + nodeCount * 0.6);
    graphRef.current.d3Force('charge', forceManyBody().strength(chargeStrength).distanceMax(600));

    const linkForce = graphRef.current.d3Force('link');
    if (linkForce) linkForce.distance(50).strength(0.25);

    graphRef.current.d3ReheatSimulation();
  }, [ForceGraphComponent, filteredData]);

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
      filteredData.links.forEach((l: any) => {
        const src = typeof l.source === 'object' ? l.source.id : l.source;
        const tgt = typeof l.target === 'object' ? l.target.id : l.target;
        if (src === focusNodeId) ids.add(tgt);
        if (tgt === focusNodeId) ids.add(src);
      });
      return ids;
    }
    if (selectedEdgeId) {
      const edge = filteredData.links.find((l: any) => l.id === selectedEdgeId);
      if (!edge) return null;
      const src = typeof edge.source === 'object' ? edge.source.id : edge.source;
      const tgt = typeof edge.target === 'object' ? edge.target.id : edge.target;
      return new Set<string>([src, tgt]);
    }
    return null;
  }, [focusNodeId, selectedEdgeId, filteredData.links]);

  // Only links touching focusNodeId itself stay colored — a link between two of its
  // neighbors (but not the focus node) still dims, matching the dimmed-node set above.
  // For an edge-driven soft focus, only that single edge stays colored.
  const isLinkTouchingFocus = useCallback((l: any) => {
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

  // Shared by the click handlers below and the sidebar's "open" action so they
  // resolve a document/external node's file + source id identically. The graph
  // node id is `doc:<title>` (see backend/api/graph.py's _doc_node), NOT
  // `doc:<sourceId>` — the real source id is node.source_id.
  // node.label is the connector's *relative* title (see parser/connectors/folder.py:
  // `title=rel_path`), which 404s against the backend's file
  // lookup for any folder-scanned source — only node.file_path (the real absolute
  // path, set from `storage_key` in diesen Connectoren) resolves. Confluence/Jira
  // store non-path strings (issue key, page title) as their storage_key, so those
  // keep using url/label instead.
  const isWebOriginSourceType = (sourceType: string | null | undefined) =>
    !!sourceType && ['confluence', 'jira'].includes(sourceType.toLowerCase());

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
  const drawNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const r = nodeRadius(node);
    const isSelected = node.id === selectedNodeId;
    const isDimmed = focusNeighborIds != null && !focusNeighborIds.has(node.id);
    const color = resolveDsColor(nodeColor(node));

    ctx.save();
    ctx.globalAlpha = isDimmed ? 0.15 : 1;

    if (isSelected) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, r + 4, 0, 2 * Math.PI);
      ctx.save();
      ctx.globalAlpha *= 0.2;
      ctx.fillStyle = color;
      ctx.fill();
      ctx.restore();
    }

    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();

    if (isSelected) {
      ctx.strokeStyle = resolveDsColor('rgb(var(--ds-white))');
      ctx.lineWidth = 1.5 / globalScale;
      ctx.stroke();
    }

    if (globalScale > 0.5) {
      const label = node.label ?? '';
      const maxLen = Math.min(12, Math.max(6, Math.floor(globalScale * 7)));
      const truncated = label.length > maxLen ? label.slice(0, maxLen) + '…' : label;
      const fontSize = Math.min(11, 8 / globalScale * 1.8);
      ctx.font = `${fontSize}px Inter, system-ui, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillStyle = resolveDsColor(isDark ? 'rgb(var(--ds-neutral-200))' : 'rgb(var(--ds-neutral-600))');
      ctx.fillText(truncated, node.x, node.y + r + 2 / globalScale);
    }
    ctx.restore();
  }, [selectedNodeId, isDark, focusNeighborIds]);

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

  // Shared between the sidebar overlay (spacious layouts) and the bottom drawer
  // (compact 3-/4-panel layouts) — only the surrounding container differs.
  // showNodeName is false in the bottom drawer, whose own collapsible header already
  // shows selectedNode.label — repeating it here would print the name twice.
  const renderDetailContent = (showNodeName: boolean) => (
    <>
      {/* Node detail */}
      {selectedNode && (
        <div className="px-3 py-3 space-y-4 flex-1">
          {showNodeName && (
            <div className="flex items-start gap-2">
              <span className="w-3 h-3 rounded-full mt-0.5 shrink-0"
                style={{ background: nodeColor(selectedNode) }} />
              <p className={cn('text-xs font-semibold leading-snug break-words', textMain)}>
                {selectedNode.label}
              </p>
            </div>
          )}

          <div className="space-y-2">
            {selectedNode.entity_type && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[10px] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.typeLabel')}</span>
                <span className={cn('text-[10px] px-1.5 py-0.5 rounded', badge)}>
                  {selectedNode.entity_type}
                </span>
              </div>
            )}
            {selectedNode.file_path && selectedNode.type === 'entity' && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[10px] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.fileLabel')}</span>
                <span className={cn('text-[10px] font-mono break-all leading-snug', textMain)}>
                  {selectedNode.file_path}
                  {selectedNode.start_line ? `:${selectedNode.start_line}` : ''}
                </span>
              </div>
            )}
            {selectedNode.source_type && (
              <div className="flex items-baseline gap-2">
                <span className={cn('text-[10px] w-14 shrink-0', textMuted)}>{t('knowledgeGraphView.sourceLabel')}</span>
                <span className={cn('text-[10px] px-1.5 py-0.5 rounded', badge)}>
                  {selectedNode.source_type}
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
                .filter((l: any) => {
                  const s = typeof l.source === 'object' ? l.source.id : l.source;
                  const t = typeof l.target === 'object' ? l.target.id : l.target;
                  return s === selectedNode.id || t === selectedNode.id;
                })
                .slice(0, 10)
                .map((l: any, i: number) => {
                  const src = resolveNode(l.source);
                  const tgt = resolveNode(l.target);
                  const other = src?.id === selectedNode.id ? tgt : src;
                  if (!other) return null;
                  return (
                    <button key={i}
                      onClick={() => { setSelectedNodeId(other.id); setSelectedEdgeId(null); }}
                      className={cn('w-full text-left flex items-center gap-2 px-1.5 py-1 rounded text-[10px] transition-colors', connRow)}>
                      <span className="w-3 shrink-0" style={{ height: 2, background: LINK_COLORS[l.link_type] ?? 'rgb(var(--ds-neutral-300))', display: 'inline-block', borderRadius: 1 }} />
                      <span className={cn('truncate', textMain)}>{other.label}</span>
                    </button>
                  );
                })}
            </div>
          </div>

          {/* Aktionen */}
          <div className="flex flex-col gap-2">
            {selectedNode.type === 'entity' && selectedNode.file_path && onFileSelect && (
              <button
                onClick={() => {
                  onFileSelect(selectedNode.file_path!, selectedNode.start_line ?? null, selectedNode.source_id ?? null);
                  onEntitySelect?.({
                    name: selectedNode.label,
                    type: selectedNode.entity_type,
                    file_path: selectedNode.file_path,
                    start_line: selectedNode.start_line,
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
                  onFileSelect(pathVal, null, sourceIdVal);
                  onDocFocus?.(pathVal, sourceIdVal, true);
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

            <button
              onClick={() => { setIsLinkPickerOpen(o => !o); setLinkCreateError(null); }}
              className="flex items-center gap-1.5 text-[11px] text-ds-indigo-400 hover:text-ds-indigo-300 transition-colors">
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
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: nodeColor(n) }} />
                      <span className={cn('truncate', textMain)}>{n.label}</span>
                      {linkPickerTargetId === n.id && <Check className="w-3 h-3 shrink-0 text-ds-indigo-400 ml-auto" />}
                    </button>
                  ))}
                  {linkPickerCandidates.length === 0 && (
                    <p className={cn('text-[10px] px-1.5 py-1', textMuted)}>{t('knowledgeGraphView.createLinkNoMatches')}</p>
                  )}
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
            <span className="w-5 shrink-0" style={{ height: 2, background: LINK_COLORS[selectedEdge.link_type] ?? 'rgb(var(--ds-neutral-300))', display: 'inline-block', borderRadius: 1 }} />
            <span className={cn('text-[10px] px-1.5 py-0.5 rounded', badge)}>
              {getLinkLabel(t, selectedEdge.link_type) ?? selectedEdge.link_type}
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
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: nodeColor(edgeSrc) }} />
                <span className={cn('font-medium truncate', textMain)}>{edgeSrc.label}</span>
              </button>
            </div>
          )}

          {edgeTgt && (
            <div>
              <p className={cn('text-[10px] mb-1', textMuted)}>{t('knowledgeGraphView.toLabel')}</p>
              <button onClick={() => { setSelectedNodeId(edgeTgt.id); setSelectedEdgeId(null); }}
                className={cn('w-full text-left flex items-center gap-2 px-1.5 py-1 rounded text-xs transition-colors', connRow)}>
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: nodeColor(edgeTgt) }} />
                <span className={cn('font-medium truncate', textMain)}>{edgeTgt.label}</span>
              </button>
            </div>
          )}

          {selectedEdge.context && (
            <div className={cn('p-2 rounded text-[10px] leading-relaxed', isDark ? 'bg-ds-zinc-800 text-ds-zinc-300' : 'bg-ds-zinc-50 text-ds-zinc-600')}>
              {selectedEdge.context}
            </div>
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
              const color = typeInfo.color;
              const label = language === 'de' ? typeInfo.labelDe : typeInfo.labelEn;
              const hidden = hiddenNodeTypes.has(type);
              return (
                <button key={type} onClick={() => toggleNodeType(type)}
                  className={cn('flex items-center gap-1.5 px-2 py-0.5 rounded-sm border text-[10px] transition-all', chipBase,
                    hidden ? 'opacity-30' : 'opacity-100')}>
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
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
              const color = LINK_COLORS[type] ?? 'rgb(var(--ds-neutral-300))';
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

        {/* Right: focus indicator + counts + controls */}
        <div className="ml-auto flex items-center gap-1.5 shrink-0">
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
          <button onClick={() => loadOverview()}
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
            <div className="absolute inset-0 flex items-center justify-center">
              <Loader2 className={cn('w-6 h-6 animate-spin', textMuted)} />
            </div>
          )}

          {!isLoading && rawNodes.length === 0 && (
            <div className={cn('absolute inset-0 flex flex-col items-center justify-center gap-2', textMuted)}>
              <BookOpen className="w-10 h-10 opacity-25" />
              <p className="text-sm">{t('knowledgeGraphView.noApprovedLinks')}</p>
              <p className="text-xs opacity-60">{t('knowledgeGraphView.noApprovedLinksHint')}</p>
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
              nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(node.x, node.y, 10, 0, 2 * Math.PI);
                ctx.fill();
              }}
              linkColor={(l: any) => {
                if (!isLinkTouchingFocus(l)) return isDark ? 'rgba(161,161,170,0.06)' : 'rgba(161,161,170,0.12)';
                return resolveDsColor(LINK_COLORS[l.link_type] ?? 'rgb(var(--ds-neutral-500))');
              }}
              linkWidth={(l: any) => l.id === selectedEdgeId ? 3.5 : Math.max(1.2, (l.score ?? 0.5) * 3)}
              linkDirectionalArrowLength={(l: any) => (l.id.startsWith('edl:') || l.id.startsWith('ref:')) ? 4 : 0}
              linkDirectionalArrowRelPos={1}
              linkCurvature={(l: any) => l.id.startsWith('kl:') ? 0.12 : 0}
              onNodeClick={(node: any) => {
                setSelectedNodeId(prev => prev === node.id ? null : node.id);
                setSelectedEdgeId(null);
                if (node.type === 'entity') {
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
                  if (onEntitySelect) {
                    onEntitySelect({
                      name: node.label,
                      type: node.entity_type,
                      file_path: node.file_path,
                      start_line: node.start_line,
                    });
                  }
                } else if (node.type === 'document' || node.type === 'external') {
                  const { pathVal, sourceIdVal } = resolveDocSelector(node);
                  // Wie im Entity-Zweig: nur anstupsen, nicht öffnen (openIfMissing=false).
                  if (onFileSelect) onFileSelect(pathVal, null, sourceIdVal, false);
                  onDocFocus?.(pathVal, sourceIdVal, false);
                }
              }}
              onLinkClick={(link: any) => {
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
              "absolute bottom-4 left-4 z-20 rounded-lg border p-3 shadow-lg transition-all backdrop-blur-md max-w-[220px] select-none",
              isDark ? "bg-ds-zinc-900/85 border-ds-zinc-800 text-ds-zinc-200" : "bg-ds-white/85 border-ds-zinc-200 text-ds-zinc-800"
            )}>
              <div className="flex items-center justify-between gap-4 cursor-pointer" onClick={() => setIsLegendOpen(o => !o)}>
                <div className="flex items-center gap-1.5">
                  <Workflow className="w-3.5 h-3.5 text-ds-indigo-500 animate-pulse" />
                  <span className="text-xs font-bold uppercase tracking-wide">
                    {language === 'de' ? 'Legende' : 'Legend'}
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
                      {language === 'de' ? 'Knoten' : 'Nodes'}
                    </p>
                    {nodeTypes.map(type => {
                      const typeInfo = UNIFIED_NODE_TYPES[type];
                      if (!typeInfo) return null;
                      const label = language === 'de' ? typeInfo.labelDe : typeInfo.labelEn;
                      return (
                        <div key={type} className="flex items-center gap-2 text-[10px]">
                          <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: typeInfo.color }} />
                          <span className="truncate">{label}</span>
                        </div>
                      );
                    })}
                  </div>

                  {/* List visible link types */}
                  {linkTypes.length > 0 && (
                    <div className={cn("space-y-1.5 pt-2 border-t", isDark ? "border-ds-zinc-800/60" : "border-ds-zinc-200")}>
                      <p className="text-[9px] uppercase tracking-wider text-ds-zinc-500 font-semibold">
                        {language === 'de' ? 'Verbindungen' : 'Links'}
                      </p>
                      {linkTypes.map(type => {
                        const color = LINK_COLORS[type] ?? 'rgb(var(--ds-neutral-300))';
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
                  ? (selectedNode.type === 'entity' ? t('knowledgeGraphView.codeEntityLabel') : t('knowledgeGraphView.documentLabel'))
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
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: nodeColor(selectedNode) }} />
              )}
              {selectedEdge && !selectedNode && (
                <span className="w-4 shrink-0" style={{ height: 2, background: LINK_COLORS[selectedEdge.link_type] ?? 'rgb(var(--ds-neutral-300))', display: 'inline-block', borderRadius: 1 }} />
              )}
              <span className={cn('text-xs font-semibold truncate flex-1', textMain)}>
                {selectedNode ? selectedNode.label : (selectedEdge ? (getLinkLabel(t, selectedEdge.link_type) ?? selectedEdge.link_type) : '')}
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
