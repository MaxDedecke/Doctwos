import { forceCollide, forceLink, forceManyBody, forceRadial, forceSimulation } from 'd3-force-3d';
import { chargeStrength, CHARGE_DISTANCE_MAX, collisionRadius, GRAPH_ALPHA_DECAY, linkDistance, radialRadius } from './graphLayout';
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
  const simulation = forceSimulation<LayoutNode>(nodes, 2).stop()
    .alphaDecay(GRAPH_ALPHA_DECAY).velocityDecay(0.3)
    .force('charge', forceManyBody<LayoutNode>()
      .strength(node => chargeStrength(nodes.length, node.degree)).distanceMax(CHARGE_DISTANCE_MAX))
    .force('collide', forceCollide<LayoutNode>(node => collisionRadius(node.radius, node.degree)).iterations(nodes.length > 2000 ? 1 : 2))
    .force('radial', forceRadial<LayoutNode>(node => radialRadius(node.degree)).strength(0.12))
    .force('link', forceLink(request.links).id((node: LayoutNode) => node.id)
      .distance((edge: { source: string | LayoutNode; target: string | LayoutNode }) => {
        const source = typeof edge.source === 'object' ? edge.source : byId.get(edge.source)!;
        const target = typeof edge.target === 'object' ? edge.target : byId.get(edge.target)!;
        return linkDistance(source.degree, target.degree);
      }).strength(0.12));
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
