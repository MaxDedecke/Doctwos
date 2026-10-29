import { ArrowLeft, X } from 'lucide-react';
import { useEffect, useRef, type ReactNode, type RefObject } from 'react';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';

interface Props {
  title: string;
  isDark: boolean;
  mode: 'side' | 'bottom' | 'sheet' | 'tools';
  height?: number;
  autoFocus?: boolean;
  returnFocusRef?: RefObject<HTMLButtonElement>;
  /** Shown as a back arrow before the title, e.g. from an edge back to the node it was opened from. */
  back?: { label: string; onBack: () => void };
  onClose: () => void;
  children: ReactNode;
}

/** A bounded, scrollable panel. Its identity survives changes of size and mode. */
export function GraphToolPanel({ title, isDark, mode, height, autoFocus, returnFocusRef, back, onClose, children }: Props) {
  const { t } = useLanguage();
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!autoFocus) return;
    const previous = document.activeElement;
    const fallback = returnFocusRef?.current;
    const panel = closeRef.current?.closest('section');
    closeRef.current?.focus();
    return () => {
      // Switching tools via the toolbar may already have focused another
      // control/menu. Restoring focus must not close that newly opened menu.
      if (document.activeElement !== document.body && document.activeElement !== previous && !panel?.contains(document.activeElement)) return;
      // Menu items can remain connected during their exit animation; the
      // durable toolbar trigger is a safer destination than that old item.
      if (fallback?.isConnected) fallback.focus();
      else if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, [autoFocus, returnFocusRef]);

  return (
    <section aria-label={title} data-testid="graph-tool-panel" data-mode={mode}
      onKeyDown={event => {
        // React events from the manual-link portal bubble through this tree,
        // although its dialog is outside this section in the DOM.
        // A just-closed menu can still prevent Escape during its exit
        // animation. The tools surface is already the active layer then.
        if (event.key === 'Escape' && (mode === 'tools' || !event.defaultPrevented) && event.currentTarget.contains(event.target as Node)) {
          event.preventDefault();
          event.stopPropagation();
          onClose();
        }
      }}
      className={cn('z-30 flex min-h-0 min-w-0 flex-col border shadow-xl',
        mode === 'side' ? 'relative w-80 shrink-0 border-y-0 border-r-0' : mode === 'bottom' ? 'relative shrink-0 border-x-0 border-b-0' : 'absolute inset-y-0 right-0 w-full',
        mode === 'tools' && 'max-w-sm',
        isDark ? 'border-ds-zinc-800 bg-ds-zinc-900 text-ds-zinc-100' : 'border-ds-zinc-200 bg-ds-white text-ds-zinc-900')}
      style={mode === 'bottom' ? { height } : undefined}>
      <div className={cn('flex shrink-0 items-center gap-2 border-b px-3 py-2', isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200')}>
        {back && (
          <button onClick={back.onBack} title={back.label} aria-label={back.label} data-testid="graph-tool-panel-back"
            className="shrink-0 rounded p-1 hover:bg-ds-zinc-500/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ds-indigo-400">
            <ArrowLeft className="h-4 w-4" />
          </button>
        )}
        <h3 className="min-w-0 flex-1 truncate text-xs font-semibold" title={title}>{title}</h3>
        <button ref={closeRef} onClick={onClose} title={t('knowledgeGraphView.closePanel')} aria-label={t('knowledgeGraphView.closePanel')}
          className="shrink-0 rounded p-1 hover:bg-ds-zinc-500/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ds-indigo-400">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain" data-testid="graph-tool-panel-body">{children}</div>
    </section>
  );
}
