import { describe, expect, it } from 'vitest';
import { decideAutoGroups } from './autoGroupExpansion';
import type { GraphViewport } from './knowledgeGraphRendering';

const view = (k: number, x = 0, y = 0): GraphViewport => ({ x, y, k, width: 900, height: 600 });
const group = (key: string, r: number, x = 0, y = 0) => ({ key, r, x, y });

describe('decideAutoGroups', () => {
  it('expands only the group zoomed towards once it fills an eighth of the view', () => {
    // r = 100 graph units: at k = 0.375 the group is 75 px wide, an eighth of 600 px.
    const groups = [group('c1', 100), group('c2', 100, 300)];
    expect(decideAutoGroups(groups, view(0.375), new Set()).expand?.key).toBe('c1');
    expect(decideAutoGroups(groups, view(0.375), new Set(), { x: 310, y: 20 }).expand?.key).toBe('c2');
    expect(decideAutoGroups(groups, view(0.3), new Set()).expand).toBeUndefined();
    // A large neighbour next to the pointer stays closed.
    expect(decideAutoGroups(groups, view(1), new Set(), { x: 150, y: 0 }).expand).toBeUndefined();
  });

  it('never decides to collapse anything when zooming out', () => {
    expect(decideAutoGroups([group('c1', 100)], view(0.05), new Set())).toEqual({ released: [], expand: undefined });
  });

  it('keeps groups closed by hand shut until they were small once', () => {
    expect(decideAutoGroups([group('c1', 100)], view(1), new Set(['c1'])).expand).toBeUndefined();
    expect(decideAutoGroups([group('c1', 100)], view(0.2), new Set(['c1'])).released).toEqual([]);
    expect(decideAutoGroups([group('c1', 100)], view(0.1), new Set(['c1'])).released).toEqual(['c1']);
  });
});
