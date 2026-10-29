import { useState } from 'react';

/**
 * „Neueste Anfrage gewinnt“: `begin()` startet eine Anfrage und liefert die Prüfung, ob ihre Antwort
 * noch gilt. Jede spätere Anfrage und jedes `invalidate()` (z. B. ein Projektwechsel) entwertet die
 * früheren, damit eine zu spät ankommende Antwort keinen neueren Stand überschreibt.
 */
export type RequestGate = { begin: () => () => boolean; invalidate: () => void };

export function createRequestGate(): RequestGate {
  let current = 0;
  return {
    begin() {
      const token = ++current;
      return () => token === current;
    },
    invalidate() {
      current += 1;
    },
  };
}

/** Ein Gate, das über alle Renders derselben Komponente bestehen bleibt. */
export function useRequestGate(): RequestGate {
  const [gate] = useState(createRequestGate);
  return gate;
}
