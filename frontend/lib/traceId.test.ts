/**
 * O-073 — die Trace-ID muss aus genau der Antwort kommen, die fehlgeschlagen
 * ist. Die beiden hier getrennt geprüften Wege sind der Kern des Punktes:
 * `extractTraceId` für den Fehler-Toast (belegt), `getLastTraceId` für den
 * Crash-Reporter (nächstgelegene Spur, bewusst unschärfer).
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { extractTraceId, getLastTraceId, rememberTraceId, rememberTraceIdFromHeaders, resetLastTraceIdForTests } from './traceId';

describe('extractTraceId', () => {
  it('liest die ID aus einem axios-Fehler mit einfachem Header-Objekt', () => {
    const error = { response: { status: 500, headers: { 'x-request-id': 'abc123' } } };

    expect(extractTraceId(error)).toBe('abc123');
  });

  it('liest die ID aus AxiosHeaders (Header-Container mit get())', () => {
    const headers = { get: (name: string) => (name === 'x-request-id' ? 'from-getter' : null) };
    const error = { response: { status: 502, headers } };

    expect(extractTraceId(error)).toBe('from-getter');
  });

  it('liest die ID aus einer nativen Response (fetch-Weg: SSE, Downloads)', () => {
    const response = { ok: false, headers: new Headers({ 'X-Request-ID': 'sse-42' }) };

    expect(extractTraceId(response)).toBe('sse-42');
  });

  it('liest eine ID, die schon am Fehler hängt (Chat-Stream wirft einen eigenen Error)', () => {
    const error = Object.assign(new Error('HTTP 500'), { traceId: 'streamed' });

    expect(extractTraceId(error)).toBe('streamed');
  });

  it('gibt null zurück, wenn kein Serveraufruf dahintersteht', () => {
    // Genau dieser Fall ist der Grund für die Trennung: ein clientseitiger
    // Fehler darf im Toast KEINE ID zeigen, sonst nennt der Nutzer dem Support
    // eine ID, die auf einen fremden Request zeigt.
    expect(extractTraceId(new Error('Zwischenablage nicht verfügbar'))).toBeNull();
    expect(extractTraceId(undefined)).toBeNull();
    expect(extractTraceId('abc123')).toBeNull();
    expect(extractTraceId({ response: { status: 500, headers: {} } })).toBeNull();
  });

  it('behandelt einen leeren Header wie einen fehlenden', () => {
    expect(extractTraceId({ response: { headers: { 'x-request-id': '   ' } } })).toBeNull();
  });
});

describe('getLastTraceId', () => {
  beforeEach(() => {
    resetLastTraceIdForTests();
  });

  it('ist null, solange keine Antwort gesehen wurde', () => {
    expect(getLastTraceId()).toBeNull();
  });

  it('merkt sich die zuletzt gesehene ID -- auch die einer erfolgreichen Antwort', () => {
    rememberTraceIdFromHeaders(new Headers({ 'x-request-id': 'erste' }));
    rememberTraceIdFromHeaders({ 'x-request-id': 'zweite' });

    expect(getLastTraceId()).toBe('zweite');
  });

  it('überschreibt eine bekannte ID nicht mit einer fehlenden', () => {
    rememberTraceId('bekannt');
    rememberTraceIdFromHeaders(new Headers());

    expect(getLastTraceId()).toBe('bekannt');
  });
});
