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
  it('lässt Dokumente sichtbar, wenn nur ihre verknüpften Code-Knoten ausgeblendet sind', () => {
    const result = filterVisibleGraph(nodes, edges, { ...base, onlyLinked: true });
    expect(result.nodes.map(n => n.id)).toEqual(['doc:jira']);
    expect(result.links).toEqual([]);
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
  });

  it('zeigt ohne onlyLinked auch unverbundene Knoten', () => {
    const result = filterVisibleGraph(nodes, edges, { isNodeHidden: () => false, isEdgeHidden: () => false, onlyLinked: false });
    expect(result.nodes).toHaveLength(4);
  });
});
