/** Fundstelle einer Dokumentstelle (Abschnitt, Seite, Zeilen) für den Link-Manager. */
export interface DocLocation {
  section: string | null;
  page: number | null;
  start_line: number | null;
  end_line: number | null;
}

type Translate = (key: string, vars?: Record<string, string | number>) => string;

/** "Kapitel › Abschnitt · Seite 2 · Zeilen 11–15"; leer, wenn nichts bekannt ist. */
export function formatDocLocation(location: DocLocation | null | undefined, t: Translate): string {
  if (!location) return '';
  const parts: string[] = [];
  if (location.section) parts.push(location.section.split(' > ').join(' › '));
  if (location.page) parts.push(t('linkManagerView.location.page', { page: location.page }));
  const { start_line: from, end_line: to } = location;
  if (from) {
    parts.push(
      to && to !== from
        ? t('linkManagerView.location.lines', { from, to })
        : t('linkManagerView.location.line', { line: from })
    );
  }
  return parts.join(' · ');
}
