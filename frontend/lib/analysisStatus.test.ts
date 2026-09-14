/**
 * O-120: formatAnalysisStatusTooltip() baut den Tooltip-Text fürs Datei-
 * Baum-/Zitat-/Graph-Badge -- mit und ohne Gründe.
 */
import { describe, expect, it } from 'vitest';
import { formatAnalysisStatusTooltip } from './analysisStatus';

const fakeT = (key: string, vars?: Record<string, string | number>) => {
  const labels: Record<string, string> = {
    'analysisStatus.partial': 'Teilweise analysiert',
    'analysisStatus.skipped': 'Analyse übersprungen',
    'analysisStatus.tooltipWithReasons': '{{label}}: {{reasons}}',
  };
  let out = labels[key] ?? key;
  for (const [k, v] of Object.entries(vars || {})) {
    out = out.replace(`{{${k}}}`, String(v));
  }
  return out;
};

describe('formatAnalysisStatusTooltip', () => {
  it('gibt nur das Label zurück, wenn keine Gründe vorliegen', () => {
    expect(formatAnalysisStatusTooltip({ status: 'skipped', reasons: [] }, fakeT)).toBe(
      'Analyse übersprungen'
    );
  });

  it('hängt die Gründe an, wenn welche vorliegen', () => {
    expect(
      formatAnalysisStatusTooltip(
        { status: 'partial', reasons: ['mismatched input', 'unbekannte compiler_family'] },
        fakeT
      )
    ).toBe('Teilweise analysiert: mismatched input; unbekannte compiler_family');
  });
});
