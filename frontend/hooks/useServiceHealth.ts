"use client";
import { api, API_URL } from '@/app/services/api';
import { useEffect, useState } from 'react';

const POLL_MS = 10000;

/**
 * Prüfergebnisse von `GET /health` (Datenbank, Redis, aktives LLM), solange `enabled` gilt.
 * Der Endpunkt antwortet bei Teilausfall mit 503 und trotzdem mit JSON; `checks` bleibt dann gefüllt.
 * `null` heißt: noch keine Antwort oder Backend nicht erreichbar.
 */
export function useServiceHealth(enabled: boolean) {
  const [checks, setChecks] = useState<Record<string, string> | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const load = async () => {
      try {
        const response = await api.fetch(`${API_URL}/health`);
        const data = await response.json() as { checks?: Record<string, string> };
        if (!cancelled) setChecks(data.checks ?? null);
      } catch {
        if (!cancelled) setChecks(null);
      }
    };
    load();
    const timer = setInterval(load, POLL_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [enabled]);

  return checks;
}
