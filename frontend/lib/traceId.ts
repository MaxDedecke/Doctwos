/**
 * O-073 — Trace-ID (`X-Request-ID`) für den Nutzer sichtbar machen.
 *
 * Das Backend erzeugt je Request eine Trace-ID, schreibt sie in jede Logzeile
 * (`core/tracing.py`) und gibt sie als `X-Request-ID` zurück. Bisher las sie
 * niemand: wer einen Fehler meldete, hatte keine ID, die er nennen konnte, und
 * der Support musste über Zeitstempel und Zuruf eingrenzen.
 *
 * Hier steht die Leseseite. Zwei getrennte Wege, mit Absicht:
 *
 *   * `extractTraceId(cause)` — die ID GENAU des Aufrufs, der fehlgeschlagen
 *     ist. Nur so darf ein Fehler-Toast eine ID anzeigen; sonst nennt er dem
 *     Nutzer eine ID, die auf einen anderen Request zeigt.
 *   * `getLastTraceId()` — die zuletzt überhaupt gesehene ID. Nur für den
 *     Crash-Reporter (`app/error.tsx`): dort gibt es kein Fehlerobjekt, wohl
 *     aber ein Interesse daran, in der Nähe des Absturzes zu landen.
 */

export const TRACE_ID_HEADER = 'x-request-id';

let lastTraceId: string | null = null;

function normalize(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

/** Header-Container von axios (AxiosHeaders oder einfaches Objekt) und fetch (Headers). */
function readHeader(headers: unknown): string | null {
  if (!headers || typeof headers !== 'object') return null;
  const getter = (headers as { get?: unknown }).get;
  if (typeof getter === 'function') {
    return normalize((getter as (name: string) => unknown).call(headers, TRACE_ID_HEADER));
  }
  const bag = headers as Record<string, unknown>;
  return normalize(bag[TRACE_ID_HEADER]) ?? normalize(bag['X-Request-ID']);
}

export function rememberTraceId(traceId: unknown): void {
  const normalized = normalize(traceId);
  if (normalized) lastTraceId = normalized;
}

export function rememberTraceIdFromHeaders(headers: unknown): void {
  rememberTraceId(readHeader(headers));
}

export function getLastTraceId(): string | null {
  return lastTraceId;
}

/**
 * Trace-ID des fehlgeschlagenen Aufrufs — aus einem axios-Fehler, einer
 * nativen `Response` oder einem Objekt, das die ID schon mitbringt. Alles
 * andere (Client-seitige Fehler ohne Serveraufruf) ergibt `null`: dann zeigt
 * der Toast bewusst keine ID an, statt eine fremde zu nennen.
 */
export function extractTraceId(cause: unknown): string | null {
  if (!cause || typeof cause !== 'object') return null;

  const asError = cause as { response?: unknown; headers?: unknown; traceId?: unknown };
  const fromResponse = readHeader((asError.response as { headers?: unknown } | undefined)?.headers);
  if (fromResponse) return fromResponse;

  const fromHeaders = readHeader(asError.headers);
  if (fromHeaders) return fromHeaders;

  return normalize(asError.traceId);
}

/** Nur für Tests: der Modulzustand überlebt sonst zwischen Testfällen. */
export function resetLastTraceIdForTests(): void {
  lastTraceId = null;
}
