import { describe, expect, it } from 'vitest';
import { AUTO_EXPAND_MAX, decideAutoGroups, type AutoGroupState } from './autoGroupExpansion';
import type { GraphViewport } from './knowledgeGraphRendering';

const view = (k: number, x = 0, y = 0): GraphViewport => ({ x, y, k, width: 900, height: 600 });
const state = (auto: [string, number][] = [], suppressed: string[] = []): AutoGroupState => ({
  auto: new Map(auto.map(([key, r]) => [key, { x: 0, y: 0, r }])),
  suppressed: new Set(suppressed),
});
const group = (key: string, r: number, x = 0, y = 0) => ({ key, r, x, y });

describe('decideAutoGroups', () => {
  it('expands the largest group that fills a third of the view and has its centre in view', () => {
    // r = 100 graph units: at k = 1 the group is 200 px wide, a third of 600 px.
    expect(decideAutoGroups([group('c1', 100), group('c2', 60)], view(1), state()).expand?.key).toBe('c1');
    expect(decideAutoGroups([group('c1', 100)], view(0.9), state()).expand).toBeUndefined();
    expect(decideAutoGroups([group('c1', 100, 2000)], view(1), state()).expand).toBeUndefined();
  });

  it('collapses with hysteresis: only when the group became small or left the view', () => {
    expect(decideAutoGroups([], view(0.5), state([['c1', 100]])).collapse).toEqual([]);
    expect(decideAutoGroups([], view(0.3), state([['c1', 100]])).collapse).toEqual(['c1']);
    expect(decideAutoGroups([], view(1, 5000), state([['c1', 100]])).collapse).toEqual(['c1']);
  });

  it('keeps manually collapsed groups shut until they were small once, and caps automatic groups', () => {
    expect(decideAutoGroups([group('c1', 100)], view(1), state([], ['c1'])).expand).toBeUndefined();
    expect(decideAutoGroups([group('c1', 100)], view(0.3), state([], ['c1'])).released).toEqual(['c1']);
    const full = state(Array.from({ length: AUTO_EXPAND_MAX }, (_, i) => [`a${i}`, 100] as [string, number]));
    expect(decideAutoGroups([group('c9', 300)], view(1), full).expand).toBeUndefined();
  });
});
