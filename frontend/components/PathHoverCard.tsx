import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn, copyToClipboard } from '@/lib/utils';
import { Check, Copy, ExternalLink } from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

const OPEN_DELAY_MS = 200;
const CLOSE_DELAY_MS = 150;
const CARD_WIDTH_PX = 448;
const VIEWPORT_MARGIN_PX = 8;
const MIN_SPACE_ABOVE_PX = 130;

/** Führt die zuletzt geplante Aktion nach ihrer Verzögerung aus; neuere ersetzen ältere. */
function useDelayedAction() {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancel = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);
  const schedule = useCallback((action: () => void, delay: number) => {
    cancel();
    timerRef.current = setTimeout(action, delay);
  }, [cancel]);
  useEffect(() => cancel, [cancel]);
  return { schedule, cancel };
}

/** Gehört auf das auslösende Element (Button o. Ä.). */
export interface PathCardTrigger {
  ref: React.RefCallback<HTMLElement>;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onFocus: () => void;
  onBlur: () => void;
  onKeyDown: (event: React.KeyboardEvent) => void;
}

interface PathHoverCardProps {
  path: string;
  theme: string;
  /** Zusätzlicher Hinweis unter dem Pfad. */
  note?: string;
  /** Ohne Angabe gibt es die Aktion „Ansehen“ nicht. */
  onView?: () => void;
  children: (trigger: PathCardTrigger) => React.ReactNode;
}

/**
 * Zeigt beim Überfahren oder Fokussieren eines gekürzten Dateinamens den vollen Pfad mit den
 * Aktionen „Pfad kopieren“ und „Ansehen“. Die Karte liegt im Portal, damit Tabellen und
 * Scrollbereiche sie nicht abschneiden.
 */
export const PathHoverCard: React.FC<PathHoverCardProps> = ({ path, theme, note, onView, children }) => {
  const { t } = useLanguage();
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const [copied, setCopied] = useState(false);
  const [triggerElement, setTriggerElement] = useState<HTMLElement | null>(null);
  const [card, setCard] = useState<HTMLDivElement | null>(null);
  const { schedule, cancel } = useDelayedAction();
  const show = () => schedule(() => setAnchor(triggerElement?.getBoundingClientRect() ?? null), OPEN_DELAY_MS);
  const hide = () => schedule(() => setAnchor(null), CLOSE_DELAY_MS);

  useEffect(() => {
    if (!anchor) return;
    const close = () => setAnchor(null);
    window.addEventListener('scroll', close, true);
    return () => window.removeEventListener('scroll', close, true);
  }, [anchor]);

  const actionClass = cn(
    'flex items-center gap-1.5 rounded px-2 py-1 font-medium transition-colors',
    theme === 'dark' ? 'text-ds-zinc-300 hover:bg-ds-zinc-800' : 'text-ds-zinc-750 hover:bg-ds-zinc-100',
  );

  return (
    <>
      {children({
        ref: setTriggerElement,
        onMouseEnter: show,
        onMouseLeave: hide,
        onFocus: show,
        onBlur: hide,
        onKeyDown: (event) => {
          if (event.key === 'Escape') setAnchor(null);
          // Die Karte liegt im Portal; ohne das erreicht die Tastatur ihre Aktionen nicht.
          if (event.key === 'Tab' && !event.shiftKey && anchor && card) {
            event.preventDefault();
            card.querySelector('button')?.focus();
          }
        },
      })}
      {anchor && typeof document !== 'undefined' && createPortal(
        <div
          ref={setCard}
          role="group"
          aria-label={path}
          onMouseEnter={cancel}
          onMouseLeave={hide}
          onFocus={cancel}
          onBlur={hide}
          onKeyDown={(event) => {
            if (event.key !== 'Escape') return;
            setAnchor(null);
            triggerElement?.focus();
          }}
          style={{
            position: 'fixed',
            zIndex: 1000,
            left: Math.max(
              VIEWPORT_MARGIN_PX,
              Math.min(anchor.left, window.innerWidth - VIEWPORT_MARGIN_PX - Math.min(CARD_WIDTH_PX, window.innerWidth - 2 * VIEWPORT_MARGIN_PX)),
            ),
            ...(anchor.top > MIN_SPACE_ABOVE_PX ? { bottom: window.innerHeight - anchor.top + 4 } : { top: anchor.bottom + 4 }),
          }}
          className={cn(
            'w-[min(28rem,calc(100vw-1rem))] rounded-md border p-2 text-xs shadow-xl',
            theme === 'dark' ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-200' : 'border-ds-zinc-200 bg-ds-white text-ds-zinc-800',
          )}
        >
          <p className="break-all px-2 py-1 font-mono">{path}</p>
          {note && <p className="px-2 pb-1 text-[0.6875rem] opacity-70">{note}</p>}
          <div className="mt-1 flex flex-wrap items-center gap-1">
            <button
              type="button"
              className={actionClass}
              onClick={async () => {
                if (!await copyToClipboard(path)) return;
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}
            >
              {copied ? <Check className="h-3.5 w-3.5 text-ds-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? t('common.copied') : t('pathCard.copy')}
            </button>
            {onView && (
              <button
                type="button"
                className={actionClass}
                onClick={() => {
                  setAnchor(null);
                  onView();
                }}
              >
                <ExternalLink className="h-3.5 w-3.5" />
                {t('pathCard.view')}
              </button>
            )}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
};
