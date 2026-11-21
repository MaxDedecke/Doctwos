import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { chatScrollTarget, FOLLOW_THRESHOLD_PX } from '@/lib/chatReveal';

/**
 * Mitscrollen im Chat: folgt wachsendem Inhalt nur, solange man unten ist, und nie weiter, als dass
 * der Anker (das Element mit `data-chat-anchor`, die letzte Frage) oben im Bild bleibt. Eine neue
 * Nachricht holt den Chat wieder nach unten. ``following`` sagt, ob man unten ist; ``scrollToLatest`` springt
 * ans Ende und folgt wieder.
 */
export function useChatFollowScroll(contentRef: RefObject<HTMLElement | null>, messageCount: number) {
  const followingRef = useRef(true);
  const followRef = useRef<() => void>(() => {});
  const viewportRef = useRef<HTMLElement | null>(null);
  const [following, setFollowing] = useState(true);

  useEffect(() => {
    const content = contentRef.current;
    const viewport = content?.closest<HTMLElement>('[data-radix-scroll-area-viewport]');
    if (!content || !viewport) return;
    viewportRef.current = viewport;
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
        setFollowing(followingRef.current);
        return;
      }
      followingRef.current = viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop <= FOLLOW_THRESHOLD_PX;
      setFollowing(followingRef.current);
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

  const scrollToLatest = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    followingRef.current = true;
    setFollowing(true);
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' });
  }, []);
  return { following, scrollToLatest };
}
