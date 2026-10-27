import { describe, expect, it, vi } from 'vitest';
import { simulateGraph } from './knowledgeGraphSimulation';
import type { LayoutResult } from './knowledgeGraphLayout';

describe('graph simulation', () => {
  it('finishes with finite positions while preserving explicitly pinned nodes', async () => {
    const result = await new Promise<LayoutResult>(resolve => {
      simulateGraph({ nodes: [
        { id: 'a', degree: 1, radius: 20, fx: 123, fy: 456 },
        { id: 'b', degree: 1, radius: 20 },
      ], links: [{ source: 'a', target: 'b' }] }, update => { if (update.done) resolve(update); });
    });
    expect(result.positions[0]).toEqual({ id: 'a', x: 123, y: 456 });
    expect(result.positions.every(p => Number.isFinite(p.x) && Number.isFinite(p.y))).toBe(true);
  });

  it('does not publish results after cancellation', async () => {
    const emit = vi.fn();
    const cancel = simulateGraph({ nodes: [{ id: 'a', degree: 0, radius: 20 }], links: [] }, emit);
    cancel();
    await new Promise(resolve => setTimeout(resolve, 30));
    expect(emit).not.toHaveBeenCalled();
  });
});
