import { describe, expect, it } from 'vitest';
import {
  clampWorkspacePercent,
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
});
