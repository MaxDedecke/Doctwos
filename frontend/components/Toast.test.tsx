/**
 * O-073 — der Fehler-Toast zeigt die Trace-ID des fehlgeschlagenen Aufrufs an,
 * damit ein Nutzer beim Melden eine ID nennen kann, die der Support im Log
 * wiederfindet. Genauso wichtig: ein Toast ohne Serveraufruf zeigt keine an.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { Toast } from './Toast';

function renderToast(toast: { message: string; type: string; traceId?: string | null }) {
  return render(
    <LanguageProvider>
      <Toast toast={toast} theme="dark" />
    </LanguageProvider>
  );
}

describe('Toast (O-073)', () => {
  it('zeigt die Trace-ID eines fehlgeschlagenen Serveraufrufs samt Hinweis an', () => {
    renderToast({ message: 'Datei konnte nicht geladen werden', type: 'error', traceId: 'a1b2c3d4' });

    expect(screen.getByText('Datei konnte nicht geladen werden')).toBeTruthy();
    expect(screen.getByText(/a1b2c3d4/)).toBeTruthy();
    expect(screen.getByText(/Fehler-ID/)).toBeTruthy();
  });

  it('zeigt ohne Trace-ID nur die Meldung -- keine leere "Fehler-ID:"-Zeile', () => {
    renderToast({ message: 'Kein Platz für ein weiteres Panel', type: 'error', traceId: null });

    expect(screen.getByText('Kein Platz für ein weiteres Panel')).toBeTruthy();
    expect(screen.queryByText(/Fehler-ID/)).toBeNull();
  });

  it('bleibt für Erfolgsmeldungen unverändert', () => {
    renderToast({ message: 'Sitzung gespeichert', type: 'success' });

    expect(screen.getByText('Sitzung gespeichert')).toBeTruthy();
    expect(screen.queryByText(/Fehler-ID/)).toBeNull();
  });
});
