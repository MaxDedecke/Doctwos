/**
 * O-073 — der Crash-Reporter. Ein Render-Absturz hat kein Fehlerobjekt eines
 * Serveraufrufs; die zuletzt gesehene Trace-ID ist die nächstgelegene Spur.
 * Sie wird dem Nutzer angezeigt UND mitgeschickt, damit Meldung und Logzeile
 * an derselben ID hängen.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { rememberTraceId, resetLastTraceIdForTests } from '@/lib/traceId';
import ErrorBoundary from './error';

function renderBoundary() {
  return render(
    <LanguageProvider>
      <ErrorBoundary error={Object.assign(new Error('Boom'), { digest: 'dig-1' })} reset={() => {}} />
    </LanguageProvider>
  );
}

describe('ErrorBoundary (O-073)', () => {
  beforeEach(() => {
    resetLastTraceIdForTests();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('zeigt die zuletzt gesehene Trace-ID an', () => {
    rememberTraceId('letzte-id');

    renderBoundary();

    expect(screen.getByText(/letzte-id/)).toBeTruthy();
  });

  it('schickt die Trace-ID im Fehlerbericht mit', async () => {
    rememberTraceId('letzte-id');
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);

    renderBoundary();
    fireEvent.click(screen.getByText('Fehlerbericht senden'));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(String(fetchMock.mock.calls[0][1].body));
    expect(body).toMatchObject({ message: 'Boom', digest: 'dig-1', trace_id: 'letzte-id' });
  });

  it('bleibt ohne Trace-ID benutzbar -- ein Absturz vor dem ersten Aufruf hat keine', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);

    renderBoundary();

    expect(screen.queryByText(/Fehler-ID/)).toBeNull();

    fireEvent.click(screen.getByText('Fehlerbericht senden'));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body)).trace_id).toBeNull();
  });
});
