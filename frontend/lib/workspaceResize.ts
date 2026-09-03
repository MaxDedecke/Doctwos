export const MIN_WORKSPACE_PANEL_PERCENT = 20;
export const MAX_WORKSPACE_PANEL_PERCENT = 80;

/**
 * Minimum width (as a percentage of the container) for a single column in the
 * 3-col layout's two-divider resize. Lower than MIN_WORKSPACE_PANEL_PERCENT
 * because three columns share the same 100%, unlike the two-panel split.
 */
export const MIN_THREE_COL_PANEL_PERCENT = 15;

/** Keep every resized panel large enough to remain usable. */
export function clampWorkspacePercent(percent: number): number {
  if (!Number.isFinite(percent)) return 50;
  return Math.max(MIN_WORKSPACE_PANEL_PERCENT, Math.min(MAX_WORKSPACE_PANEL_PERCENT, percent));
}

/** Convert a pointer coordinate into a bounded percentage of an axis. */
export function pointerToWorkspacePercent(pointer: number, start: number, size: number): number {
  if (!Number.isFinite(size) || size <= 0) return 50;
  return clampWorkspacePercent(((pointer - start) / size) * 100);
}

/** Convert a pointer coordinate into a raw 0-100 percentage, clamped only to the axis bounds. */
export function pointerToPercent(pointer: number, start: number, size: number): number {
  if (!Number.isFinite(size) || size <= 0) return 50;
  return Math.max(0, Math.min(100, ((pointer - start) / size) * 100));
}

/**
 * Clamp a percentage between explicit bounds. Unlike clampWorkspacePercent's
 * fixed 20/80 range, the 3-col dividers need bounds that shift with the other
 * divider's current position (each column must stay >= MIN_THREE_COL_PANEL_PERCENT).
 */
export function clampPercentBetween(percent: number, min: number, max: number): number {
  if (!Number.isFinite(percent)) return (min + max) / 2;
  if (min > max) return min;
  return Math.max(min, Math.min(max, percent));
}
