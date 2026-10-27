import { canvasColor, resolveDsColor } from './designTokens';
import { getGraphEdgeColor, getGraphNodeColor, normalizeGraphEdgeDirection } from './graphTaxonomy';
import { arrowLength, BIDIRECTIONAL_ARROW_HALF_WIDTH_RATIO, edgeLineWidth, NODE_RADIUS_SCALE } from './graphLayout';
import type { GraphEdge, GraphNode } from './knowledgeGraphTypes';
import { drawKnowledgeNodeIcon } from '@/components/KnowledgeNodeIcon';

export const graphEndId = (end: GraphEdge['source']) => typeof end === 'object' ? end.id : end;
export const graphEdgeType = (edge: GraphEdge) => edge.relation_type ?? edge.link_type;
export function graphEdgeDirection(edge: GraphEdge) {
  const fallback = /^(code:|edl:|ref:)/.test(edge.id) ? 'directed' : 'undirected';
  return normalizeGraphEdgeDirection(edge.direction, fallback);
}
export const isEdgeDirected = (edge: GraphEdge) => graphEdgeDirection(edge) !== 'undirected';

export function nodeRadius(node: GraphNode, degree = 0): number {
  const base = node.type === 'entity' || node.type === 'code_file' ? 8 : 7;
  return (base + Math.min(9, Math.sqrt(degree) * 1.8)) * NODE_RADIUS_SCALE;
}

export function getNodeDisplayLabel(node: GraphNode): string {
  return node.type === 'code_file' && node.file_path
    ? node.file_path.split(/[\\/]/).filter(Boolean).pop() || node.label : node.label;
}

export type GraphViewport = { x: number; y: number; k: number; width: number; height: number };
type RenderOptions = {
  nodes: GraphNode[]; links: GraphEdge[]; degrees: Map<string, number>; ghostIds: Set<string>;
  selectedNodeId: string | null; selectedEdgeId: string | null; focusNodeId: string | null;
  focusNeighborIds: Set<string> | null; isDark: boolean;
  styleRevision?: string;
  viewport: () => GraphViewport | null; zoom: () => number;
};

/** Snapshot CSS and topology once. No DOM reads or graph searches during a frame. */
export function createKnowledgeGraphRenderer(options: RenderOptions) {
  const { nodes, links, degrees, ghostIds, selectedNodeId, selectedEdgeId, focusNodeId,
    focusNeighborIds, isDark, viewport, zoom } = options;
  const byId = new Map(nodes.map(node => [node.id, node]));
  const colors = new Map<string, string>();
  const resolve = (value: string) => {
    if (!colors.has(value)) colors.set(value, resolveDsColor(value));
    return colors.get(value)!;
  };
  const accent = canvasColor('accent');
  const foreground = canvasColor('foreground');
  const ghost = canvasColor('neutral-400');
  const ghostLink = canvasColor('neutral-400', 0.45);
  const outline = canvasColor(isDark ? 'white' : 'neutral-900', isDark ? 0.4 : 0.5);
  const labelColor = canvasColor(isDark ? 'neutral-200' : 'neutral-600');
  const dimLink = canvasColor('neutral-400', isDark ? 0.06 : 0.12);
  const nodeStyles = new Map(nodes.map(node => [node.id, {
    radius: nodeRadius(node, degrees.get(node.id) ?? 0), label: getNodeDisplayLabel(node),
    color: ghostIds.has(node.id) ? ghost : resolve(getGraphNodeColor(node)),
  }]));
  const edgeColors = new Map(links.map(edge => [edge.id, resolve(getGraphEdgeColor(graphEdgeType(edge)))]));
  const resolveNode = (end: GraphEdge['source']) => typeof end === 'object' ? end : byId.get(end);
  const radius = (node: GraphNode) => nodeStyles.get(node.id)?.radius ?? nodeRadius(node);

  const pairs = new Map<string, GraphEdge[]>();
  const pairKey = (edge: GraphEdge) => {
    const a = graphEndId(edge.source), b = graphEndId(edge.target);
    return a < b ? `${a}--${b}` : `${b}--${a}`;
  };
  links.forEach(edge => {
    const key = pairKey(edge);
    if (!pairs.has(key)) pairs.set(key, []);
    pairs.get(key)!.push(edge);
  });
  const curvatures = new Map<string, number>();
  pairs.forEach(pair => pair.forEach((edge, index) => {
    let curvature = edge.id.startsWith('kl:') ? 0.08 : 0;
    if (pair.length === 2) {
      curvature = graphEndId(pair[0].source) !== graphEndId(pair[1].source) ? 0.2 : index === 0 ? 0.2 : -0.2;
    } else if (pair.length > 2) {
      curvature = ((index - (pair.length - 1) / 2) / (pair.length - 1)) * 0.4 || 0.05;
    }
    curvatures.set(edge.id, curvature);
  }));

  function nodeVisible(node: GraphNode) {
    const view = viewport();
    if (!view || node.x == null || node.y == null) return true;
    // Include label/selection padding. Nodes retain their physics outside the viewport.
    const padding = radius(node) + 180 / Math.max(view.k, 0.01);
    return Math.abs(node.x - view.x) <= view.width / (2 * view.k) + padding
      && Math.abs(node.y - view.y) <= view.height / (2 * view.k) + padding;
  }

  function linkVisible(edge: GraphEdge) {
    const view = viewport();
    const source = resolveNode(edge.source), target = resolveNode(edge.target);
    if (!view || !source || !target || source.x == null || target.x == null || source.y == null || target.y == null) return true;
    // Keep crossing edges even if both endpoints are outside. Curves use a conservative margin.
    const curveMargin = Math.hypot(target.x - source.x, target.y - source.y) * Math.abs(curvatures.get(edge.id) ?? 0);
    const halfW = view.width / (2 * view.k) + 60 / view.k + curveMargin;
    const halfH = view.height / (2 * view.k) + 60 / view.k + curveMargin;
    return Math.max(source.x, target.x) >= view.x - halfW && Math.min(source.x, target.x) <= view.x + halfW
      && Math.max(source.y, target.y) >= view.y - halfH && Math.min(source.y, target.y) <= view.y + halfH;
  }

  function linkColor(edge: GraphEdge) {
    if (edge.id === selectedEdgeId) return accent;
    if (ghostIds.has(graphEndId(edge.source)) || ghostIds.has(graphEndId(edge.target))) return ghostLink;
    const focus = selectedNodeId ?? focusNodeId;
    const touchesFocus = focus ? graphEndId(edge.source) === focus || graphEndId(edge.target) === focus
      : !selectedEdgeId || edge.id === selectedEdgeId;
    return touchesFocus ? edgeColors.get(edge.id)! : dimLink;
  }

  function drawNode(node: GraphNode, ctx: CanvasRenderingContext2D, scale: number) {
    const style = nodeStyles.get(node.id)!;
    const primary = node.id === selectedNodeId || node.id === focusNodeId;
    const dimmed = focusNeighborIds != null && !focusNeighborIds.has(node.id);
    const x = node.x ?? 0, y = node.y ?? 0, r = style.radius;
    ctx.save();
    ctx.globalAlpha = dimmed ? 0.15 : ghostIds.has(node.id) ? 0.4 : 1;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = style.color;
    ctx.fill();
    if (primary || r * scale >= 5) {
      ctx.lineWidth = Math.min(1.6 / scale, r * 0.18);
      ctx.strokeStyle = primary ? accent : outline;
      ctx.stroke();
    }
    if (primary) {
      ctx.beginPath();
      ctx.arc(x, y, r + 4 / scale, 0, Math.PI * 2);
      ctx.strokeStyle = accent;
      ctx.lineWidth = 2 / scale;
      ctx.stroke();
    }
    if (r * scale >= 9) drawKnowledgeNodeIcon(node, ctx, scale, NODE_RADIUS_SCALE, r);
    if ((scale > 0.45 && !dimmed) || primary) {
      ctx.font = `${primary ? '600 ' : ''}${primary ? 11 / scale : Math.min(11, 14.4 / scale)}px Inter, system-ui, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillStyle = primary ? foreground : labelColor;
      ctx.fillText(style.label, x, y + r + 3 / scale);
    }
    ctx.restore();
  }

  function edgeArrowLength(edge: GraphEdge) {
    const source = resolveNode(edge.source), target = resolveNode(edge.target);
    const selected = edge.id === selectedEdgeId;
    let exposedLength: number | null = null;
    if (source?.x != null && target?.x != null && source.y != null && target.y != null) {
      exposedLength = Math.hypot(target.x - source.x, target.y - source.y) - radius(source) - radius(target);
      if (!selected && exposedLength * zoom() < 12) return 0;
    }
    const smallestRadius = Math.min(source ? radius(source) : Infinity, target ? radius(target) : Infinity);
    return arrowLength({ selected, lineWidth: edgeLineWidth(selected, edge.score), zoom: zoom(),
      exposedLength, maxLength: Number.isFinite(smallestRadius) ? smallestRadius : null });
  }

  function arrowRelPos(edge: GraphEdge) {
    if (!isEdgeDirected(edge)) return 0.5;
    const source = resolveNode(edge.source), target = resolveNode(edge.target);
    if (source?.x != null && target?.x != null && source.y != null && target.y != null) {
      const distance = Math.hypot(target.x - source.x, target.y - source.y);
      if (distance > 0) return Math.max(0.1, Math.min(0.95, 1 - (radius(target) + 1) / distance));
    }
    return 0.88;
  }

  function drawSourceArrow(edge: GraphEdge, ctx: CanvasRenderingContext2D) {
    if (graphEdgeDirection(edge) !== 'bidirectional') return;
    const source = resolveNode(edge.source), target = resolveNode(edge.target);
    if (source?.x == null || target?.x == null || source.y == null || target.y == null) return;
    const distance = Math.hypot(source.x - target.x, source.y - target.y);
    const size = edgeArrowLength(edge);
    if (!distance || !size) return;
    const ux = (source.x - target.x) / distance, uy = (source.y - target.y) / distance;
    const tipX = source.x + ux * (radius(source) + 1), tipY = source.y + uy * (radius(source) + 1);
    const width = size * BIDIRECTIONAL_ARROW_HALF_WIDTH_RATIO;
    ctx.save();
    ctx.fillStyle = linkColor(edge);
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(tipX - ux * size - uy * width, tipY - uy * size + ux * width);
    ctx.lineTo(tipX - ux * size + uy * width, tipY - uy * size - ux * width);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  return { drawNode, linkColor, nodeVisible, linkVisible, drawSourceArrow,
    arrowLength: (edge: GraphEdge) => isEdgeDirected(edge) ? edgeArrowLength(edge) : 0,
    arrowRelPos, curvature: (edge: GraphEdge) => curvatures.get(edge.id) ?? 0 };
}
