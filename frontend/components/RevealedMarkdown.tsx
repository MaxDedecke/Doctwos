'use client';

import { useEffect, useRef, useState } from 'react';
import { MarkdownContent } from '@/components/MarkdownContent';
import { nextRevealLength } from '@/lib/chatReveal';

type Props = React.ComponentProps<typeof MarkdownContent> & {
  /** Die Antwort entsteht gerade (letzte Nachricht, Anfrage läuft). */
  live: boolean;
};

function prefersReducedMotion() {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Blendet eine live entstehende Antwort zügig ein (siehe lib/chatReveal.ts). Gespeicherte
 * Antworten erscheinen sofort. Das Einblenden läuft zu Ende, auch wenn die Anfrage schon vorher
 * abgeschlossen ist: Die Antwort kommt oft erst mit dem Ende des Streams.
 */
export function RevealedMarkdown({ live, content, ...rest }: Props) {
  const [revealing, setRevealing] = useState(live);
  const [length, setLength] = useState(live ? 0 : content.length);
  const [previous, setPrevious] = useState(content);
  const lengthRef = useRef(length);

  if (live && !revealing) setRevealing(true);
  if (previous !== content) {
    setPrevious(content);
    // Eine andere Nachricht an dieser Stelle (Sitzungswechsel) ist keine entstehende Antwort.
    if (!live && !content.startsWith(previous)) setRevealing(false);
  }

  const animate = revealing && !prefersReducedMotion();
  useEffect(() => {
    if (!animate || lengthRef.current >= content.length) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const next = nextRevealLength(lengthRef.current, content, now - last);
      last = now;
      lengthRef.current = next;
      setLength(next);
      if (next < content.length) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [animate, content]);

  const visible = animate ? content.slice(0, Math.min(length, content.length)) : content;
  return <MarkdownContent content={visible} {...rest} />;
}
