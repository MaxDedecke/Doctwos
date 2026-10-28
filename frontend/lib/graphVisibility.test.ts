import { describe, expect, it } from 'vitest';
import { filterVisibleGraph } from './graphVisibility';

const nodes = [
  { id: 'file:1', type: 'code_file' },
  { id: 'file:2', type: 'code_file' },
  { id: 'doc:jira', type: 'document' },
  { id: 'doc:alone', type: 'document' },
];
const edges = [
  { id: 'e1', source: 'doc:jira', target: 'file:1', kind: 'documented' },
  { id: 'e2', source: 'file:1', target: 'file:2', kind: 'code' },
];
const base = { isNodeHidden: (n: { type: string }) => n.type === 'code_file', isEdgeHidden: () => false };

describe('filterVisibleGraph', () => {
  it('keeps an insight without resolvable edges unless its type is hidden', () => {
    const insights = [{ id: 'insight:1', type: 'insight' }];
    expect(filterVisibleGraph(insights, [], { isNodeHidden: () => false, isEdgeHidden: () => false, onlyLinked: true }).nodes).toEqual(insights);
    expect(filterVisibleGraph(insights, [], { isNodeHidden: () => true, isEdgeHidden: () => false, onlyLinked: true }).nodes).toEqual([]);
  });

  it('zeigt ausgeblendete Nachbarn sichtbarer Knoten als Platzhalter mit ihrer Kante', () => {
    const result = filterVisibleGraph(nodes, edges, { ...base, onlyLinked: true });
    expect(result.nodes.map(n => n.id)).toEqual(['file:1', 'doc:jira']);
    expect([...result.ghostIds]).toEqual(['file:1']);
    expect(result.links.map(e => e.id)).toEqual(['e1']);
  });

  it('lässt Kanten zwischen zwei Platzhaltern weg', () => {
    const result = filterVisibleGraph(nodes, edges, { ...base, onlyLinked: true });
    expect(result.nodes.map(n => n.id)).not.toContain('file:2');
    expect(result.links.map(e => e.id)).not.toContain('e2');
  });

  it('hat ohne ausgeblendete Knotenarten keine Platzhalter', () => {
    const result = filterVisibleGraph(nodes, edges, { isNodeHidden: () => false, isEdgeHidden: () => false, onlyLinked: true });
    expect(result.ghostIds.size).toBe(0);
  });

  it('entfernt Knoten ohne jede Verbindung weiterhin', () => {
    const result = filterVisibleGraph(nodes, edges, { isNodeHidden: () => false, isEdgeHidden: () => false, onlyLinked: true });
    expect(result.nodes.map(n => n.id)).not.toContain('doc:alone');
    expect(result.links).toHaveLength(2);
  });

  it('entfernt Knoten, deren Verbindungen alle über ausgeblendete Kantenarten laufen', () => {
    const result = filterVisibleGraph(nodes, edges, {
      isNodeHidden: () => false,
      isEdgeHidden: edge => edge.kind === 'documented',
      onlyLinked: true,
    });
    expect(result.nodes.map(n => n.id)).toEqual(['file:1', 'file:2']);
    expect(result.ghostIds.size).toBe(0);
  });

  it('zeigt ohne onlyLinked auch unverbundene Knoten', () => {
    const result = filterVisibleGraph(nodes, edges, { isNodeHidden: () => false, isEdgeHidden: () => false, onlyLinked: false });
    expect(result.nodes).toHaveLength(4);
  });
});
