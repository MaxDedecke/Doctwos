import { describe, expect, it } from 'vitest';
import {
  clampPercentBetween,
  clampWorkspacePercent,
  pointerToPercent,
  pointerToWorkspacePercent,
} from './workspaceResize';

describe('workspace resize helpers', () => {
  it('keeps panel ratios inside the usable range', () => {
    expect(clampWorkspacePercent(5)).toBe(20);
    expect(clampWorkspacePercent(65)).toBe(65);
    expect(clampWorkspacePercent(95)).toBe(80);
  });

  it('converts pointer coordinates for both horizontal and vertical axes', () => {
    expect(pointerToWorkspacePercent(250, 0, 500)).toBe(50);
    expect(pointerToWorkspacePercent(0, 100, 500)).toBe(20);
    expect(pointerToWorkspacePercent(600, 100, 500)).toBe(80);
  });

  it('converts pointer coordinates to a raw percentage without the 20/80 clamp', () => {
    expect(pointerToPercent(250, 0, 500)).toBe(50);
    // Unlike pointerToWorkspacePercent, values near the edges are only
    // bounded to [0, 100] -- the 3-col dividers need to reach further than
    // 20/80 since three columns share the same 100%.
    expect(pointerToPercent(0, 100, 500)).toBe(0);
    expect(pointerToPercent(600, 100, 500)).toBe(100);
  });

  it('falls back to the axis midpoint for a degenerate (zero-width) container', () => {
    expect(pointerToPercent(100, 0, 0)).toBe(50);
    expect(pointerToWorkspacePercent(100, 0, 0)).toBe(50);
  });

  it('clamps a percentage between explicit, shifting bounds', () => {
    expect(clampPercentBetween(40, 15, 51.67)).toBe(40);
    expect(clampPercentBetween(5, 15, 51.67)).toBe(15);
    expect(clampPercentBetween(90, 15, 51.67)).toBeCloseTo(51.67);
  });

  it('does not invert a degenerate bound pair (min > max) into a nonsensical result', () => {
    // Can arise transiently if a caller passes a stale "other boundary" --
    // must return the lower bound rather than silently picking `max` (which
    // would put the divider on the wrong side of the one it must not cross).
    expect(clampPercentBetween(40, 60, 50)).toBe(60);
  });
});
