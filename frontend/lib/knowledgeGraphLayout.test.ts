import { describe, expect, it } from 'vitest';
import { neighborhoodPositions } from './knowledgeGraphLayout';
import type { GraphNode, GraphEdge } from './knowledgeGraphTypes';

const node = (id: string): GraphNode => ({ id, type: 'entity', label: id });
const edge = (source: string, target: string, direction: GraphEdge['direction'] = 'directed'): GraphEdge => ({
  id: `${source}:${target}`, source, target, direction, link_type: 'code_dependency', score: null, context: null,
});

describe('neighborhood layout', () => {
  it('respects incoming/outgoing direction and follows undirected connections in both modes', () => {
    const nodes = ['a', 'b', 'c', 'd'].map(node);
    const links = [edge('a', 'b'), edge('c', 'a'), edge('b', 'd', 'undirected')];
    const out = neighborhoodPositions(nodes, links, 'a', 'outgoing');
    expect(out.get('b')!.x).toBeGreaterThan(0);
    expect(out.get('d')!.x).toBeGreaterThan(out.get('b')!.x);
    expect(out.get('c')!.x).toBe(0);
    const incoming = neighborhoodPositions(nodes, links, 'a', 'incoming');
    expect(incoming.get('c')!.x).toBeLessThan(0);
    expect(incoming.get('b')!.x).toBeCloseTo(0);
  });

  it('handles a 20,000-node cycle without recursion or repeated edge scans', () => {
    const count = 20000;
    const nodes = Array.from({ length: count }, (_, i) => node(String(i)));
    const edges = nodes.map((n, i) => edge(n.id, String((i + 1) % count)));
    let reads = 0;
    const links = edges.map(e => new Proxy(e, { get(target, key, receiver) {
      if (key === 'source' || key === 'target') reads++;
      return Reflect.get(target, key, receiver);
    } }));
    const positions = neighborhoodPositions(nodes, links, '0', 'outgoing');
    expect(positions.size).toBe(count);
    expect(positions.get(String(count - 1))!.x).toBeGreaterThan(positions.get('1')!.x);
    expect(reads).toBeLessThanOrEqual(count * 2);
  });
});
