import { afterEach, describe, expect, it } from 'vitest';
import {
  BRANDING_STYLE_ID,
  DEFAULT_BRANDING,
  brandingCss,
  brandingTitle,
  contrast,
  deriveAccentTokens,
  getBranding,
  hexToRgb,
  setBranding,
  statusColorConflict,
} from './branding';

const parse = (channels: string) => channels.split(' ').map(Number) as [number, number, number];

describe('deriveAccentTokens', () => {
  it('keeps a colour that already has enough contrast', () => {
    const tokens = deriveAccentTokens('#0064d2')!;
    expect(tokens.light['--ds-accent']).toBe('0 100 210');
  });

  it.each(['#ffd400', '#7fdbff', '#e4002b', '#00a651', '#ffffff', '#000000'])(
    'reaches WCAG AA in both themes for %s',
    (hex) => {
      const tokens = deriveAccentTokens(hex)!;
      expect(contrast(parse(tokens.light['--ds-accent']), [255, 255, 255])).toBeGreaterThanOrEqual(4.5);
      expect(contrast(parse(tokens.dark['--ds-accent']), [14, 30, 30])).toBeGreaterThanOrEqual(4.5);
      expect(contrast(parse(tokens.dark['--ds-accent']), parse(tokens.dark['--ds-on-accent']))).toBeGreaterThanOrEqual(4.5);
    },
  );

  it('rejects anything that is not #RRGGBB', () => {
    expect(deriveAccentTokens('red')).toBeNull();
    expect(hexToRgb('#12345')).toBeNull();
  });
});

describe('statusColorConflict', () => {
  it('flags colours close to error, warning and success', () => {
    expect(statusColorConflict('#e4002b')).toBe('danger');
    expect(statusColorConflict('#f59e0b')).toBe('warning');
    expect(statusColorConflict('#059669')).toBe('success');
  });

  it('ignores blue, violet and greys', () => {
    expect(statusColorConflict('#0064d2')).toBeNull();
    expect(statusColorConflict('#7a2e8c')).toBeNull();
    expect(statusColorConflict('#808080')).toBeNull();
  });
});

describe('brandingCss and title', () => {
  it('is empty without an accent colour', () => {
    expect(brandingCss(DEFAULT_BRANDING)).toBe('');
  });

  it('overrides light and dark accent tokens', () => {
    const css = brandingCss({ accent_color: '#7a2e8c' });
    expect(css).toContain(':root{--ds-accent:');
    expect(css).toContain(':root.dark{--ds-accent:');
  });

  it('adds the customer name to the title', () => {
    expect(brandingTitle({ customer_name: 'Beispielkunde' })).toBe('Codena – Beispielkunde');
    expect(brandingTitle({ customer_name: null })).toBe('Codena – Code Knowledge System');
  });
});

describe('setBranding', () => {
  afterEach(() => setBranding(null));

  it('applies style and title immediately', () => {
    setBranding({ customer_name: 'Beispielkunde', accent_color: '#7a2e8c' });
    expect(getBranding().customer_name).toBe('Beispielkunde');
    expect(document.getElementById(BRANDING_STYLE_ID)?.textContent).toContain('--ds-accent');
    expect(document.title).toBe('Codena – Beispielkunde');
  });
});
