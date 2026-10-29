import { describe, expect, it } from 'vitest';
import { decideAutoGroups } from './autoGroupExpansion';
import type { GraphViewport } from './knowledgeGraphRendering';

const view = (k: number, x = 0, y = 0): GraphViewport => ({ x, y, k, width: 900, height: 600 });
const group = (key: string, r: number, x = 0, y = 0) => ({ key, r, x, y });

describe('decideAutoGroups', () => {
  it('expands the largest group that fills a third of the view and has its centre in view', () => {
    // r = 100 graph units: at k = 1 the group is 200 px wide, a third of 600 px.
    expect(decideAutoGroups([group('c1', 100), group('c2', 60)], view(1), new Set()).expand?.key).toBe('c1');
    expect(decideAutoGroups([group('c1', 100)], view(0.9), new Set()).expand).toBeUndefined();
    expect(decideAutoGroups([group('c1', 100, 2000)], view(1), new Set()).expand).toBeUndefined();
  });

  it('never decides to collapse anything when zooming out', () => {
    expect(decideAutoGroups([group('c1', 100)], view(0.05), new Set())).toEqual({ released: [], expand: undefined });
  });

  it('keeps groups closed by hand shut until they were small once', () => {
    expect(decideAutoGroups([group('c1', 100)], view(1), new Set(['c1'])).expand).toBeUndefined();
    expect(decideAutoGroups([group('c1', 100)], view(0.3), new Set(['c1'])).released).toEqual(['c1']);
  });
});
