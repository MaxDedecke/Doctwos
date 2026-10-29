import { forceCollide, forceLink, forceManyBody, forceRadial, forceSimulation, forceX, forceY } from 'd3-force-3d';
import { chargeStrength, CHARGE_DISTANCE_MAX, collisionRadius, GRAPH_ALPHA_DECAY, INCREMENTAL_ANCHOR_STRENGTH,
  INCREMENTAL_CHARGE_FACTOR, INCREMENTAL_COLLIDE_PADDING, INCREMENTAL_PINNED_LINK_STRENGTH, linkDistance, radialRadius } from './graphLayout';
import { seedPositions, type LayoutRequest, type LayoutResult, type LayoutNode } from './knowledgeGraphLayout';

/** Runs in a worker; the async batches also provide a responsive fallback without Worker support. */
export function simulateGraph(request: LayoutRequest, emit: (result: LayoutResult) => void) {
  const nodes = request.nodes;
  seedPositions(nodes);
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const publish = (done: boolean) => emit({ done,
    positions: nodes.map(node => ({ id: node.id, x: node.x!, y: node.y! })) });
  if (nodes.every(node => node.fx != null && node.fy != null)) {
    publish(true);
    return () => {};
  }
  const byId = new Map(nodes.map(node => [node.id, node]));
  // With fixed neighbors (nodes added to an existing layout), the global rings would drag the new
  // nodes away from the node they were loaded for.
  const incremental = nodes.some(node => node.fx != null && node.fy != null);
  // Neu dazugekommene Knoten bleiben bei ihrer Startposition (um die aufgeklappte Gruppe). Kanten zu
  // fest stehenden Knoten ziehen nur schwach, sonst reißt jede Kante zu einer fernen Gruppe ihre
  // Datei quer durch den Graphen.
  const pinned = (node: LayoutNode) => node.fx != null && node.fy != null;
  const start = new Map(nodes.map(node => [node.id, { x: node.x!, y: node.y! }]));
  const simulation = forceSimulation<LayoutNode>(nodes, 2).stop()
    .alphaDecay(GRAPH_ALPHA_DECAY).velocityDecay(0.3)
    .force('charge', forceManyBody<LayoutNode>()
      .strength(node => chargeStrength(nodes.length, node.degree) * (incremental && !pinned(node) ? INCREMENTAL_CHARGE_FACTOR : 1))
      .distanceMax(CHARGE_DISTANCE_MAX))
    .force('collide', forceCollide<LayoutNode>(node => incremental && !pinned(node)
      ? node.radius + INCREMENTAL_COLLIDE_PADDING : collisionRadius(node.radius, node.degree)).iterations(nodes.length > 2000 ? 1 : 2))
    .force('radial', incremental ? null : forceRadial<LayoutNode>(node => radialRadius(node.degree)).strength(0.12))
    .force('link', forceLink(request.links).id((node: LayoutNode) => node.id)
      .distance((edge: { source: string | LayoutNode; target: string | LayoutNode }) => {
        const source = typeof edge.source === 'object' ? edge.source : byId.get(edge.source)!;
        const target = typeof edge.target === 'object' ? edge.target : byId.get(edge.target)!;
        return linkDistance(source.degree, target.degree);
      }).strength((edge: { source: string | LayoutNode; target: string | LayoutNode }) => {
        if (!incremental) return 0.12;
        const source = typeof edge.source === 'object' ? edge.source : byId.get(edge.source)!;
        const target = typeof edge.target === 'object' ? edge.target : byId.get(edge.target)!;
        return pinned(source) || pinned(target) ? INCREMENTAL_PINNED_LINK_STRENGTH : 0.12;
      }))
    .force('anchorX', incremental ? forceX<LayoutNode>(node => start.get(node.id)!.x).strength(INCREMENTAL_ANCHOR_STRENGTH) : null)
    .force('anchorY', incremental ? forceY<LayoutNode>(node => start.get(node.id)!.y).strength(INCREMENTAL_ANCHOR_STRENGTH) : null);
  const maxTicks = nodes.length > 2000 ? 100 : 180;
  let ticks = 0;
  let nextPublish = 20;
  function batch() {
    if (cancelled) return;
    const start = performance.now();
    do { simulation.tick(); ticks++; } while (ticks < maxTicks && performance.now() - start < 20);
    const done = ticks >= maxTicks;
    if (ticks >= nextPublish || done) {
      publish(done);
      nextPublish = ticks + 20;
    }
    if (!done) timer = setTimeout(batch, 0);
    else simulation.stop();
  }
  timer = setTimeout(batch, 0);
  return () => { cancelled = true; clearTimeout(timer); simulation.stop(); };
}
