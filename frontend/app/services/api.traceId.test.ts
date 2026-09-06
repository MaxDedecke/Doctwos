/**
 * O-073 — die Verkabelung: die Trace-ID muss beim Durchlaufen der zentralen
 * API-Schicht hängenbleiben, sonst nützt der beste Toast nichts. Beide Wege
 * sind abgedeckt: axios (der Normalfall) und api.fetch (SSE/Downloads).
 */
import axios from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getLastTraceId, resetLastTraceIdForTests, extractTraceId } from '@/lib/traceId';
import { api } from './api';

describe('API-Schicht merkt sich die Trace-ID (O-073)', () => {
  beforeEach(() => {
    resetLastTraceIdForTests();
    vi.unstubAllGlobals();
  });

  it('merkt sich die ID einer erfolgreichen axios-Antwort', async () => {
    axios.defaults.adapter = async (config) => ({
      data: {}, status: 200, statusText: 'OK', headers: { 'x-request-id': 'ok-1' }, config,
    });

    await api.getMe();

    expect(getLastTraceId()).toBe('ok-1');
  });

  it('merkt sich die ID einer fehlgeschlagenen axios-Antwort und lässt sie am Fehler lesbar', async () => {
    axios.defaults.adapter = async (config) => {
      const response = { data: {}, status: 500, statusText: 'Error', headers: { 'x-request-id': 'fehler-7' }, config };
      throw Object.assign(new Error('Request failed'), { isAxiosError: true, response, config });
    };

    const error = await api.getMe().then(() => null, (e) => e);

    expect(getLastTraceId()).toBe('fehler-7');
    // Genau diese ID landet im Toast -- nicht die "letzte gesehene".
    expect(extractTraceId(error)).toBe('fehler-7');
  });

  it('merkt sich die ID auch auf dem fetch-Weg (SSE, Downloads)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 500, headers: new Headers({ 'x-request-id': 'stream-9' }),
    }));

    await api.fetch('/api/chat', { method: 'POST' });

    expect(getLastTraceId()).toBe('stream-9');
  });
});
