import { useCallback, useEffect, useRef, useState } from 'react';
import { api, API_URL } from '@/app/services/api';
import { collapseExpansion, mergeExpansion, type GraphData, type GraphExpansion } from '@/lib/graphExpansion';
import type { GraphEdge, GraphNode } from '@/lib/knowledgeGraphTypes';

// Raw parser edges per page; several of them collapse into one file edge.
const PAGE_LIMIT = 500;
const MAX_PAGES_PER_CLICK = 6;

type Options = {
  graph: GraphData;
  setGraph: (graph: GraphData) => void;
  projectIdFor: (node: GraphNode) => number | null;
};

/** Loads a node's hidden connections into the current overview instead of replacing it. */
export function useGraphExpansion({ graph, setGraph, projectIdFor }: Options) {
  const [expansions, setExpansions] = useState<Map<string, GraphExpansion>>(() => new Map());
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(graph);
  useEffect(() => { latest.current = graph; }, [graph]);

  const expand = useCallback(async (node: GraphNode, anchor: { x?: number; y?: number }) => {
    const previous = expansions.get(node.id);
    if (previous && !previous.hasMore) return;
    setLoadingId(node.id);
    setError(null);
    try {
      const page: GraphData = { nodes: [], edges: [] };
      let cursor = previous?.cursor ?? null;
      let hasMore = false;
      for (let index = 0; index < MAX_PAGES_PER_CLICK; index++) {
        const params = new URLSearchParams({ node_id: node.id, status: 'approved', direction: 'both',
          relationships: 'code_dependency,documented,manual', limit: String(PAGE_LIMIT) });
        const projectId = projectIdFor(node);
        if (projectId !== null) params.set('project_id', String(projectId));
        if (cursor) params.set('cursor', cursor);
        const res = await api.fetch(`${API_URL}/graph/neighborhood?${params}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: { nodes?: GraphNode[]; edges?: GraphEdge[]; has_more?: boolean; next_cursor?: string | null } = await res.json();
        page.nodes.push(...(data.nodes ?? []));
        page.edges.push(...(data.edges ?? []));
        cursor = data.next_cursor ?? null;
        hasMore = Boolean(data.has_more) && cursor !== null;
        if (!hasMore) break;
      }
      const { graph: merged, added } = mergeExpansion(latest.current, page, { id: node.id, ...anchor }, previous);
      setGraph(merged);
      setExpansions(current => new Map(current).set(node.id, { ...added, cursor, hasMore }));
    } catch (e) {
      console.error('[KnowledgeGraph] expand in place failed', e);
      setError(node.id);
    } finally {
      setLoadingId(null);
    }
  }, [expansions, projectIdFor, setGraph]);

  const collapse = useCallback((nodeId: string) => {
    setGraph(collapseExpansion(latest.current, expansions, nodeId));
    setExpansions(current => {
      const next = new Map(current);
      next.delete(nodeId);
      return next;
    });
  }, [expansions, setGraph]);

  const reset = useCallback(() => {
    setExpansions(new Map());
    setError(null);
  }, []);

  return { expansions, loadingId, errorNodeId: error, expand, collapse, reset };
}
