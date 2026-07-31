/** Persisted project colors need a concrete CSS color for `<input type="color">`. */
export const DEFAULT_PROJECT_COLOR = "#e4002b";

/** Runtime color strings for canvas/SVG libraries that cannot consume classes. */
export const dsColor = (token: string) => `rgb(var(--ds-${token}))`;

export const resolveDsColor = (color: string) => {
  if (typeof document === 'undefined') return color;
  const match = color.match(/^rgb\(var\((--ds-[^)]+)\)\)$/);
  if (!match) return color;
  const channels = getComputedStyle(document.documentElement).getPropertyValue(match[1]).trim();
  return channels ? `rgb(${channels})` : color;
};
