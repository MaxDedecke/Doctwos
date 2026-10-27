import { describe, expect, it, vi } from 'vitest';
import { createKnowledgeGraphRenderer, type GraphViewport } from './knowledgeGraphRendering';
import type { GraphNode, GraphEdge } from './knowledgeGraphTypes';

function fixture() {
  const nodes: GraphNode[] = [
    { id: 'a', type: 'code_file', label: 'src/A.java', file_path: 'src/A.java', x: -100, y: 0 },
    { id: 'b', type: 'document', label: 'Guide', x: 100, y: 0 },
  ];
  const links: GraphEdge[] = [{ id: 'kl:1', source: 'a', target: 'b', link_type: 'manual', direction: 'bidirectional', score: null, context: null }];
  const viewport: { current: GraphViewport | null } = { current: null };
  const options: Parameters<typeof createKnowledgeGraphRenderer>[0] = { nodes, links, degrees: new Map([['a', 1], ['b', 1]]), ghostIds: new Set<string>(),
    selectedNodeId: 'a', selectedEdgeId: null, focusNodeId: null, focusNeighborIds: new Set(['a', 'b']),
    isDark: true, viewport: () => viewport.current, zoom: () => 1 };
  const ctx = Object.fromEntries(['save', 'restore', 'beginPath', 'arc', 'stroke', 'fill', 'fillText', 'ellipse',
    'moveTo', 'lineTo', 'closePath', 'rect'].map(method => [method, vi.fn()])) as unknown as CanvasRenderingContext2D;
  return { ...options, options, ctx, viewport };
}

describe('knowledge graph rendering', () => {
  it('draws nodes and arrows without DOM style reads after preparation', () => {
    const { options, nodes, links, ctx } = fixture();
    const renderer = createKnowledgeGraphRenderer(options);
    const style = vi.spyOn(window, 'getComputedStyle');
    for (let i = 0; i < 3; i++) {
      nodes.forEach(node => renderer.drawNode(node, ctx, 1));
      renderer.linkColor(links[0]);
      renderer.drawSourceArrow(links[0], ctx);
    }
    expect(style).not.toHaveBeenCalled();
    expect(ctx.fillText).toHaveBeenCalledWith('A.java', expect.any(Number), expect.any(Number));
    style.mockRestore();
  });

  it('omits tiny icons and labels but keeps a selected node labelled', () => {
    const { options, nodes, ctx } = fixture();
    const renderer = createKnowledgeGraphRenderer(options);
    renderer.drawNode(nodes[1], ctx, 0.05);
    expect(ctx.fillText).not.toHaveBeenCalled();
    expect(ctx.ellipse).not.toHaveBeenCalled();
    renderer.drawNode(nodes[0], ctx, 0.05);
    expect(ctx.fillText).toHaveBeenCalledExactlyOnceWith('A.java', expect.any(Number), expect.any(Number));
  });

  it('keeps crossing edges when both endpoints are outside the viewport', () => {
    const { options, nodes, links, viewport } = fixture();
    nodes[0].x = -1000;
    nodes[1].x = 1000;
    viewport.current = { x: 0, y: 0, k: 1, width: 300, height: 200 };
    const renderer = createKnowledgeGraphRenderer(options);
    expect(nodes.map(renderer.nodeVisible)).toEqual([false, false]);
    expect(renderer.linkVisible(links[0])).toBe(true);
    nodes.forEach(node => { node.y = 2000; });
    expect(renderer.linkVisible(links[0])).toBe(false);
    viewport.current.y = 2000;
    expect(renderer.linkVisible(links[0])).toBe(true);
  });

  it('resolves new theme colors when preparing a new renderer', () => {
    const { options, links } = fixture();
    options.selectedEdgeId = links[0].id;
    document.documentElement.style.setProperty('--ds-accent', '1 2 3');
    const before = createKnowledgeGraphRenderer(options);
    document.documentElement.style.setProperty('--ds-accent', '4 5 6');
    const after = createKnowledgeGraphRenderer(options);
    expect(before.linkColor(links[0])).toBe('rgb(1 2 3)');
    expect(after.linkColor(links[0])).toBe('rgb(4 5 6)');
    document.documentElement.style.removeProperty('--ds-accent');
  });
});
