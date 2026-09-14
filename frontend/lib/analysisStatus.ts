/**
 * frontend/lib/analysisStatus.ts
 * ================================
 * O-120: gemeinsamer Wortschatz/Formatierung für den strukturellen
 * Vollständigkeits-Status einer Datei (core.model.AnalysisStatus im Backend/
 * Parser), verwendet von den drei im Katalogeintrag genannten Oberflächen --
 * Editor-Dateibaum (FileTreeList), Chat-Zitate (MarkdownContent) und
 * Call-Graph (CallGraphView). "complete" taucht hier bewusst nicht auf: das
 * Backend liefert für uneingeschränkt analysierte Dateien gar kein Feld
 * (siehe backend/core/analysis_status.py), kein Eintrag heißt schon
 * "kein Makel bekannt".
 */

export type AnalysisStatus = 'partial' | 'text_fallback' | 'skipped' | 'error';

export interface AnalysisStatusInfo {
  status: AnalysisStatus;
  reasons: string[];
}

/** CSS-Var-Farbtoken (wie designTokens.ts::dsColor) je Status -- 'skipped' ist
 * bewusst neutral statt warnend: das ist keine inhaltliche Einschränkung wie
 * bei 'partial'/'text_fallback', sondern schlicht "nie angesehen". */
export const ANALYSIS_STATUS_COLOR_TOKEN: Record<AnalysisStatus, string> = {
  partial: 'rgb(var(--ds-warning-base))',
  text_fallback: 'rgb(var(--ds-warning-base))',
  skipped: 'rgb(var(--ds-neutral-500))',
  error: 'rgb(var(--ds-danger-base))',
};

/** Baut den Tooltip-/Titeltext aus Status + Gründen -- `t` ist der `t()` aus
 * useLanguage(), damit dieselbe Formatierung in de/en übersetzt bleibt. */
export function formatAnalysisStatusTooltip(
  info: AnalysisStatusInfo,
  t: (key: string, vars?: Record<string, string | number>) => string
): string {
  const label = t(`analysisStatus.${info.status}`);
  if (info.reasons.length === 0) return label;
  return t('analysisStatus.tooltipWithReasons', { label, reasons: info.reasons.join('; ') });
}
