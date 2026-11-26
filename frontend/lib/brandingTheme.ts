/** Öffentliches Kundenbranding (GET /config/branding). */
export interface Branding {
  customer_name: string | null;
  accent_color: string | null;
  login_notice: string | null;
  imprint_url: string | null;
  privacy_url: string | null;
  support_url: string | null;
  logo_light_url: string | null;
  logo_dark_url: string | null;
  revision: number;
}

export const DEFAULT_BRANDING: Branding = {
  customer_name: null,
  accent_color: null,
  login_notice: null,
  imprint_url: null,
  privacy_url: null,
  support_url: null,
  logo_light_url: null,
  logo_dark_url: null,
  revision: 0,
};

export const BRANDING_STYLE_ID = 'codena-branding';

declare global {
  interface Window {
    __CODENA_BRANDING__?: Partial<Branding> | null;
  }
}

type Rgb = [number, number, number];

const WHITE: Rgb = [255, 255, 255];
const BLACK: Rgb = [0, 0, 0];
// Hintergrund im Dark Mode (--ds-background in globals.css).
const DARK_BACKGROUND: Rgb = [14, 30, 30];
const DARK_ON_ACCENT: Rgb = [8, 18, 33];
const MIN_CONTRAST = 4.5;

export function hexToRgb(hex: string): Rgb | null {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex.trim());
  if (!match) return null;
  return [parseInt(match[1], 16), parseInt(match[2], 16), parseInt(match[3], 16)];
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance([r, g, b]: Rgb): number {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

function mix(a: Rgb, b: Rgb, t: number): Rgb {
  return [0, 1, 2].map((i) => Math.round(a[i] + (b[i] - a[i]) * t)) as Rgb;
}

/** Schiebt die Farbe in kleinen Schritten zu `toward`, bis sie gegen `against` genug Kontrast hat. */
function ensureContrast(color: Rgb, against: Rgb, toward: Rgb): Rgb {
  for (let t = 0; t <= 1; t += 0.04) {
    const candidate = mix(color, toward, t);
    if (contrast(candidate, against) >= MIN_CONTRAST) return candidate;
  }
  return toward;
}

const channels = (c: Rgb) => c.join(' ');

export interface AccentTokens {
  light: Record<string, string>;
  dark: Record<string, string>;
}

/**
 * Leitet aus einer Kundenfarbe alle Akzent-Tokens ab. Hell: Akzent als Fläche unter weißer
 * Schrift und als Text auf Weiß; dunkel: Akzent als Text auf dem dunklen Hintergrund.
 * Beides mit mindestens 4,5:1 (WCAG AA), notfalls abgedunkelt bzw. aufgehellt.
 */
export function deriveAccentTokens(hex: string): AccentTokens | null {
  const input = hexToRgb(hex);
  if (!input) return null;
  const light = ensureContrast(input, WHITE, BLACK);
  const dark = ensureContrast(input, DARK_BACKGROUND, WHITE);
  return {
    light: {
      '--ds-accent': channels(light),
      '--ds-focus': channels(light),
      '--ds-on-accent': channels(WHITE),
      '--ds-accent-soft': channels(mix(light, WHITE, 0.86)),
      '--ds-accent-base': channels(light),
      '--ds-accent-strong': channels(mix(light, BLACK, 0.4)),
    },
    dark: {
      '--ds-accent': channels(dark),
      '--ds-focus': channels(dark),
      '--ds-on-accent': channels(contrast(dark, DARK_ON_ACCENT) >= MIN_CONTRAST ? DARK_ON_ACCENT : WHITE),
    },
  };
}

const STATUS_HUES: { key: 'danger' | 'warning' | 'success'; hue: number }[] = [
  { key: 'danger', hue: 355 },
  { key: 'warning', hue: 38 },
  { key: 'success', hue: 155 },
];

/** Liegt die Farbe nah an einer Statusfarbe (Fehler, Warnung, Erfolg)? Nur Hinweis, keine Sperre. */
export function statusColorConflict(hex: string): 'danger' | 'warning' | 'success' | null {
  const rgb = hexToRgb(hex);
  if (!rgb) return null;
  const [r, g, b] = rgb.map((v) => v / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  const saturation = max === 0 ? 0 : delta / max;
  if (saturation < 0.35 || max < 0.25) return null;
  let hue = 0;
  if (delta > 0) {
    if (max === r) hue = 60 * (((g - b) / delta) % 6);
    else if (max === g) hue = 60 * ((b - r) / delta + 2);
    else hue = 60 * ((r - g) / delta + 4);
  }
  if (hue < 0) hue += 360;
  for (const status of STATUS_HUES) {
    const distance = Math.min(Math.abs(hue - status.hue), 360 - Math.abs(hue - status.hue));
    if (distance <= 18) return status.key;
  }
  return null;
}

/** CSS, das die Akzent-Tokens überschreibt; leer, wenn keine Kundenfarbe gesetzt ist. */
export function brandingCss(branding: Pick<Branding, 'accent_color'>): string {
  const tokens = branding.accent_color ? deriveAccentTokens(branding.accent_color) : null;
  if (!tokens) return '';
  const block = (selector: string, vars: Record<string, string>) =>
    `${selector}{${Object.entries(vars).map(([k, v]) => `${k}:${v};`).join('')}}`;
  return block(':root', tokens.light) + block(':root.dark', tokens.dark);
}

export function brandingTitle(branding: Pick<Branding, 'customer_name'>): string {
  return branding.customer_name ? `Codena – ${branding.customer_name}` : 'Codena – Code Knowledge System';
}

export function normalizeBranding(data: Partial<Branding> | null | undefined): Branding {
  return { ...DEFAULT_BRANDING, ...(data ?? {}) };
}
