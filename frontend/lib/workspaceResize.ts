export const MIN_WORKSPACE_PANEL_PERCENT = 20;
export const MAX_WORKSPACE_PANEL_PERCENT = 80;

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
