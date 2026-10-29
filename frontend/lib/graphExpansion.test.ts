import { describe, expect, it } from 'vitest';
import { canExpandInPlace, collapseExpansion, collapseGroupKeys, hiddenEdgeCounts, mergeExpansion, seedGroupPositions, type GraphData, type GraphExpansion } from './graphExpansion';
import type { GraphEdge, GraphNode } from './knowledgeGraphTypes';

const file = (id: string, degree?: number): GraphNode => ({ id, type: 'code_file', label: id, degree });
const edge = (id: string, source: string, target: string): GraphEdge => ({ id, source, target, link_type: 'code_dependency', score: null, context: null });

describe('hiddenEdgeCounts', () => {
  it('reports connections the server knows but the graph has not loaded', () => {
    const counts = hiddenEdgeCounts([file('a', 3), file('b', 1), file('c')], [edge('ab', 'a', 'b')]);
    expect(counts.get('a')).toBe(2);
    expect(counts.has('b')).toBe(false);
    expect(counts.has('c')).toBe(false);
  });
});

describe('mergeExpansion / collapseExpansion', () => {
  const base: GraphData = { nodes: [file('a', 3), file('b', 1)], edges: [edge('ab', 'a', 'b')] };
  const page: GraphData = {
    nodes: [file('a'), file('b'), file('c'), file('d')],
    edges: [edge('ab', 'a', 'b'), edge('ac', 'a', 'c'), edge('da', 'd', 'a')],
  };

  it('adds only unknown nodes and edges and keeps loaded nodes untouched', () => {
    const { graph, added } = mergeExpansion(base, page, { id: 'a', x: 100, y: -50 });
    expect(graph.nodes.map(node => node.id)).toEqual(['a', 'b', 'c', 'd']);
    expect(graph.nodes[0]).toBe(base.nodes[0]);
    expect(graph.edges.map(item => item.id)).toEqual(['ab', 'ac', 'da']);
    expect([...added.nodeIds]).toEqual(['c', 'd']);
    expect([...added.edgeIds]).toEqual(['ac', 'da']);
    expect(hiddenEdgeCounts(graph.nodes, graph.edges).get('a')).toBeUndefined();
  });

  it('places new nodes around the anchor rather than at the origin', () => {
    const { graph } = mergeExpansion(base, page, { id: 'a', x: 5000, y: 5000 });
    for (const node of graph.nodes.slice(2)) {
      expect(Math.hypot(node.x! - 5000, node.y! - 5000)).toBeLessThan(600);
    }
  });

  it('collapses exactly what the expansion added', () => {
    const { graph, added } = mergeExpansion(base, page, { id: 'a' });
    const collapsed = collapseExpansion(graph, new Map([['a', added]]), 'a');
    expect(collapsed.nodes.map(node => node.id)).toEqual(['a', 'b']);
    expect(collapsed.edges.map(item => item.id)).toEqual(['ab']);
  });

  it('keeps added nodes that a later expansion still connects', () => {
    const first = mergeExpansion(base, page, { id: 'a' });
    const second = mergeExpansion(first.graph, { nodes: [file('c'), file('e')], edges: [edge('ce', 'c', 'e')] }, { id: 'c' });
    const expansions = new Map<string, GraphExpansion>([['a', first.added], ['c', second.added]]);
    const collapsed = collapseExpansion(second.graph, expansions, 'a');
    expect(collapsed.nodes.map(node => node.id)).toEqual(['a', 'b', 'c', 'e']);
    expect(collapsed.edges.map(item => item.id)).toEqual(['ab', 'ce']);
  });

  it('offers in-place expansion only where the neighborhood endpoint resolves the node', () => {
    expect(canExpandInPlace(file('file:1:2:A.cbl'))).toBe(true);
    expect(canExpandInPlace({ id: 'doc:1:Runbook.md', type: 'document', label: 'Runbook' })).toBe(true);
    expect(canExpandInPlace({ id: 'insight:4', type: 'insight', label: 'Erkenntnis' })).toBe(false);
  });
});

describe('group positions', () => {
  const group = (key: string, extra: Partial<GraphNode> = {}): GraphNode => ({ id: `group:${key}`, type: 'group', label: key, group_key: key, ...extra });

  it('starts the contents of an expanded group around the group and keeps placed nodes', () => {
    const previous = [group('c1', { x: 1000, y: 500 }), group('c2', { x: -50, y: 0 })];
    const next = [group('c2'), { ...file('a'), group_parent: 'c1' }, { ...file('b'), group_parent: 'c1' }];
    const seeded = seedGroupPositions(next, previous);
    expect(seeded[0]).toBe(next[0]);
    for (const node of seeded.slice(1)) expect(Math.hypot(node.x! - 1000, node.y! - 500)).toBeLessThan(400);
  });

  it('returns a collapsed group to the centre of its former contents, including subgroups', () => {
    const previous = [{ ...file('a'), group_parent: 'c1', x: 0, y: 0 }, { ...group('c1.2'), group_parent: 'c1', x: 100, y: 100 },
      { ...file('b'), group_parent: 'c1.2', x: 200, y: 200 }, { ...file('z'), group_parent: 'c9', x: 9000, y: 9000 }];
    const [collapsed] = seedGroupPositions([group('c1')], previous, 'c1');
    expect([collapsed.x, collapsed.y]).toEqual([100, 100]);
    expect(collapseGroupKeys(['c1', 'c1.2', 'c10', 't4'], 'c1')).toEqual(['c10', 't4']);
  });
});
