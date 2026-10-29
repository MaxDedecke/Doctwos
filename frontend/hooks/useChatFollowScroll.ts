import { useEffect, useRef, type RefObject } from 'react';
import { chatScrollTarget, FOLLOW_THRESHOLD_PX } from '@/lib/chatReveal';

/**
 * Mitscrollen im Chat: folgt wachsendem Inhalt nur, solange man unten ist, und nie weiter, als dass
 * der Anker (das Element mit `data-chat-anchor`, die letzte Frage) oben im Bild bleibt. Eine neue
 * Nachricht holt den Chat wieder nach unten.
 */
export function useChatFollowScroll(contentRef: RefObject<HTMLElement | null>, messageCount: number) {
  const followingRef = useRef(true);
  const followRef = useRef<() => void>(() => {});

  useEffect(() => {
    const content = contentRef.current;
    const viewport = content?.closest<HTMLElement>('[data-radix-scroll-area-viewport]');
    if (!content || !viewport) return;
    let programmatic = false;
    const follow = () => {
      const anchor = content.querySelector<HTMLElement>('[data-chat-anchor="true"]');
      const anchorTop = anchor
        ? anchor.getBoundingClientRect().top - viewport.getBoundingClientRect().top + viewport.scrollTop
        : null;
      const target = chatScrollTarget({
        scrollTop: viewport.scrollTop,
        scrollHeight: viewport.scrollHeight,
        clientHeight: viewport.clientHeight,
        anchorTop,
        following: followingRef.current,
      });
      if (target == null) return;
      programmatic = true;
      viewport.scrollTop = target;
    };
    const onScroll = () => {
      // Das eigene Scrollen bis zum Anker beendet das Folgen nicht, erst das des Lesers.
      if (programmatic) {
        programmatic = false;
        return;
      }
      followingRef.current = viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop <= FOLLOW_THRESHOLD_PX;
    };
    followRef.current = follow;
    viewport.addEventListener('scroll', onScroll, { passive: true });
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(follow) : null;
    observer?.observe(content);
    return () => {
      viewport.removeEventListener('scroll', onScroll);
      observer?.disconnect();
    };
  }, [contentRef]);

  const previousCount = useRef(messageCount);
  useEffect(() => {
    if (messageCount > previousCount.current) {
      followingRef.current = true;
      followRef.current();
    }
    previousCount.current = messageCount;
  }, [messageCount]);
}
