import { describe, expect, it } from 'vitest';
import { layerWidthPercent, toggleExpanded, toggleKind } from './dropView';

describe('dropView', () => {
  it('keeps at least one edge kind and a fixed order', () => {
    expect(toggleKind(['control'], 'control')).toEqual(['control']);
    expect(toggleKind(['control'], 'includes')).toEqual(['control', 'includes']);
    expect(toggleKind(['data', 'includes'], 'control')).toEqual(['control', 'data', 'includes']);
  });
  it('widens the layers like a pyramid and never exceeds the container', () => {
    const widths = [0, 1, 2, 3].map(layer => layerWidthPercent(layer, 3));
    expect(widths).toEqual([...widths].sort((a, b) => a - b));
    expect(widths[0]).toBeLessThan(widths[3]);
    expect(Math.max(...widths)).toBe(100);
    expect(layerWidthPercent(0, 0)).toBe(100);
  });
  it('toggles expanded layers in a stable order', () => {
    expect(toggleExpanded([3], 1)).toEqual([1, 3]);
    expect(toggleExpanded([1, 3], 1)).toEqual([3]);
  });
});
