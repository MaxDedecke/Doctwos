import { useEffect, useMemo, useState } from 'react';
import { api, API_URL } from '@/app/services/api';
import { linkRunOptionsParams, type LinkRunOptions } from '@/lib/linkRunOptions';
import {
  isEmptySet, setForApi, setsForApi, setsFromServer,
  type LinkSetDef, type RunEstimate, type RunSetsDef, type SetPreview, type WorkspaceOptions,
} from '@/lib/linkSets';

// Mirrors parser/tasks/link_builder.py + cross_link_builder.py LLM_MIN_CONFIDENCE (35); der zuletzt benutzte Wert
// gilt je Browser, weil er den nächsten Lauf konfiguriert, nicht eine Projekteinstellung.
const MIN_CONFIDENCE_STORAGE_KEY = 'doctus-link-min-confidence';
const MIN_CONFIDENCE_DEFAULT = 35;
const DEBOUNCE_MS = 300;

function readStoredMinConfidence(): number {
  try {
    const parsed = parseInt(localStorage.getItem(MIN_CONFIDENCE_STORAGE_KEY) ?? '', 10);
    return Number.isFinite(parsed) && parsed >= 0 && parsed <= 100 ? parsed : MIN_CONFIDENCE_DEFAULT;
  } catch {
    return MIN_CONFIDENCE_DEFAULT;
  }
}

async function postJson<T>(url: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await api.fetch(url, {
    method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `HTTP ${response.status}`);
  return data as T;
}

/** Ergebnis eines verzögerten POST; neue Eingaben verwerfen die laufende Anfrage. */
function useDebouncedPost<T>(url: string | null, body: unknown) {
  const key = url ? `${url} ${JSON.stringify(body)}` : null;
  const [state, setState] = useState<{ key: string | null; data: T | null; error: string | null }>({ key: null, data: null, error: null });
  useEffect(() => {
    if (!key || !url) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      postJson<T>(url, body, controller.signal)
        .then(data => setState({ key, data, error: null }))
        .catch((error: Error) => { if (!controller.signal.aborted) setState({ key, data: null, error: error.message }); });
    }, DEBOUNCE_MS);
    return () => { clearTimeout(timer); controller.abort(); };
    // `key` fasst URL und Inhalt zusammen; `body` selbst ist je Render ein neues Objekt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const fresh = state.key === key;
  return { data: fresh ? state.data : null, error: fresh ? state.error : null, loading: Boolean(key) && !fresh };
}

export interface StartResult { runId?: number; error?: string }

/** Zustand der Analyse-Arbeitsfläche eines Projekts: Analyseart, Menge A/B, Vorschau, Schätzung, Laufeinstellungen. */
export function useLinkRunWorkspace(projectId: number, open: boolean, embeddingModel: string) {
  const base = `${API_URL}/projects/${projectId}/link-runs`;
  const [options, setOptions] = useState<WorkspaceOptions | null>(null);
  const [optionsError, setOptionsError] = useState(false);
  const [pairingKey, setPairingKey] = useState<string | null>(null);
  const [edited, setEdited] = useState<Record<string, RunSetsDef>>({});
  const [minConfidence, setMinConfidenceState] = useState(readStoredMinConfidence);
  const [maxItems, setMaxItems] = useState(200);
  const [runOptions, setRunOptions] = useState<LinkRunOptions>({});

  useEffect(() => {
    if (!open) return;
    let active = true;
    api.fetch(`${base}/options`)
      .then(response => (response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`))))
      .then((data: WorkspaceOptions) => {
        if (!active || !Array.isArray(data?.pairings)) return;
        setOptions(data);
        setOptionsError(false);
      })
      .catch(() => { if (active) setOptionsError(true); });
    return () => { active = false; };
  }, [base, open]);

  const pairing = options?.pairings.find(item => item.key === pairingKey) ?? options?.pairings[0] ?? null;
  const sets = useMemo(
    () => (pairing ? edited[pairing.key] ?? setsFromServer(pairing, options?.last?.[pairing.key]) : null),
    [pairing, edited, options],
  );

  const updateSet = (side: 'a' | 'b', change: (set: LinkSetDef) => LinkSetDef) => {
    if (!pairing || !sets) return;
    setEdited(previous => ({ ...previous, [pairing.key]: { ...sets, [side]: change(sets[side]) } }));
  };

  const previewA = useDebouncedPost<SetPreview>(open && sets ? `${base}/preview` : null, { set: sets ? setForApi(sets.a) : null });
  const previewB = useDebouncedPost<SetPreview>(open && sets ? `${base}/preview` : null, { set: sets ? setForApi(sets.b) : null });
  const blocked = !sets || isEmptySet(sets.a) || isEmptySet(sets.b);
  const estimate = useDebouncedPost<RunEstimate>(open && sets && !blocked ? `${base}/estimate` : null, sets ? setsForApi(sets) : null);

  const setMinConfidence = (value: number) => {
    const clamped = Math.min(100, Math.max(0, Math.round(value) || 0));
    setMinConfidenceState(clamped);
    try { localStorage.setItem(MIN_CONFIDENCE_STORAGE_KEY, String(clamped)); } catch { /* nur Komfort */ }
  };

  const start = async (): Promise<StartResult> => {
    if (!sets || blocked) return { error: 'empty' };
    try {
      const result = await postJson<{ run_id?: number }>(base, {
        ...setsForApi(sets),
        min_confidence: minConfidence,
        max_items: Math.max(1, Math.min(5000, Math.round(maxItems) || 200)),
        embedding_model: embeddingModel,
        params: linkRunOptionsParams(runOptions),
      });
      return typeof result.run_id === 'number' ? { runId: result.run_id } : { error: 'start' };
    } catch (error) {
      return { error: (error as Error).message || 'start' };
    }
  };

  return {
    options, optionsError, pairing, setPairingKey, sets, updateSet,
    previewA, previewB, estimate, blocked,
    minConfidence, setMinConfidence, maxItems, setMaxItems, runOptions, setRunOptions,
    start,
  };
}

export type LinkRunWorkspaceState = ReturnType<typeof useLinkRunWorkspace>;
