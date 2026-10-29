/**
 * Einblenden und Mitscrollen einer Chat-Antwort.
 *
 * Im Evidenz-Modus und bei Agent-Antworten schickt das Backend den Text erst nach der
 * Quellenprüfung als einen Block (backend/services/chat_turn.py). Ohne Einblenden stünde eine
 * lange Antwort schlagartig da, und das Mitscrollen spränge an ihr Ende.
 */

/** Zeichen pro Sekunde mindestens; kurze Antworten erscheinen damit wie getippt. */
export const REVEAL_MIN_CHARS_PER_SECOND = 400;
/** Ein Rückstand wird spätestens in dieser Zeit aufgeholt, auch bei sehr langen Antworten. */
export const REVEAL_MAX_SECONDS = 2;

/** Wie viele Zeichen nach `elapsedMs` sichtbar sind, gerundet auf das nächste Wortende. */
export function nextRevealLength(shown: number, text: string, elapsedMs: number): number {
  if (shown >= text.length) return text.length;
  // Am ganzen Text bemessen, nicht am Rest: sonst wird es zum Ende hin immer langsamer.
  const perSecond = Math.max(REVEAL_MIN_CHARS_PER_SECOND, text.length / REVEAL_MAX_SECONDS);
  const step = Math.max(1, Math.round((perSecond * elapsedMs) / 1000));
  let next = Math.min(text.length, shown + step);
  while (next < text.length && !/\s/.test(text[next])) next += 1;
  return next;
}

/**
 * Wohin der Chat beim Wachsen der Antwort scrollt, oder `null`, wenn er stehen bleibt.
 * Er folgt nur, wenn man unten war, nur nach unten und nie weiter, als dass der Anfang der
 * Antwort (`anchorTop`, relativ zum Inhalt) oben im Bild bleibt.
 */
export function chatScrollTarget({ scrollTop, scrollHeight, clientHeight, anchorTop, following, margin = 12 }: {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
  anchorTop: number | null;
  following: boolean;
  margin?: number;
}): number | null {
  if (!following) return null;
  const bottom = Math.max(0, scrollHeight - clientHeight);
  const target = anchorTop == null ? bottom : Math.min(bottom, Math.max(0, anchorTop - margin));
  return target > scrollTop + 1 ? target : null;
}

/** Gilt als „unten“, wer höchstens so weit über dem Ende steht. */
export const FOLLOW_THRESHOLD_PX = 80;
