import { describe, expect, it } from 'vitest';
import { formatDocLocation } from './docLocation';

const t = (key: string, vars?: Record<string, string | number>) =>
  ({
    'linkManagerView.location.page': `Seite ${vars?.page}`,
    'linkManagerView.location.lines': `Zeilen ${vars?.from}–${vars?.to}`,
    'linkManagerView.location.line': `Zeile ${vars?.line}`,
  })[key] ?? key;

describe('formatDocLocation', () => {
  it('nennt Abschnitt, Seite und Zeilenbereich', () => {
    expect(formatDocLocation({ section: 'Kapitel > Entscheidung', page: 2, start_line: 11, end_line: 15 }, t))
      .toBe('Kapitel › Entscheidung · Seite 2 · Zeilen 11–15');
  });

  it('nennt eine einzelne Zeile ohne Bereich', () => {
    expect(formatDocLocation({ section: null, page: null, start_line: 7, end_line: 7 }, t)).toBe('Zeile 7');
    expect(formatDocLocation({ section: null, page: null, start_line: 7, end_line: null }, t)).toBe('Zeile 7');
  });

  it('bleibt ohne Angaben leer', () => {
    expect(formatDocLocation(null, t)).toBe('');
    expect(formatDocLocation(undefined, t)).toBe('');
    expect(formatDocLocation({ section: null, page: null, start_line: null, end_line: null }, t)).toBe('');
  });
});
