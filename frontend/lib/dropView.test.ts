import { describe, expect, it } from 'vitest';
import { connectorPath, layerWidthPercent, toggleExpanded, toggleKind } from './dropView';

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

describe('connectorPath', () => {
  const box = (left: number, top: number) => ({ left, top, right: left + 100, bottom: top + 20 });
  const base = { left: 10, top: 10 };

  it('verbindet untereinander vom unteren zum oberen Rand', () => {
    expect(connectorPath(box(10, 10), box(10, 110), base, 'vertical')).toEqual({ d: 'M 50 20 C 50 60, 50 60, 50 100', reversed: false });
  });

  it('verbindet nebeneinander vom rechten zum linken Rand', () => {
    expect(connectorPath(box(10, 10), box(210, 10), base, 'horizontal')).toEqual({ d: 'M 100 10 C 150 10, 150 10, 200 10', reversed: false });
  });

  it('merkt sich, wenn das Ziel vor der Quelle liegt, und zeichnet immer vorwärts', () => {
    const path = connectorPath(box(210, 10), box(10, 10), base, 'horizontal');
    expect(path?.reversed).toBe(true);
    expect(path?.d.startsWith('M 100 10')).toBe(true);
  });

  it('zeichnet nichts zwischen Knoten, die sich in Laufrichtung überlappen', () => {
    expect(connectorPath(box(10, 10), box(50, 100), base, 'horizontal')).toBeNull();
    expect(connectorPath(box(10, 10), box(200, 15), base, 'vertical')).toBeNull();
  });
});

