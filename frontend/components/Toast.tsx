'use client';

import { Check, X } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import { useLanguage } from '@/lib/i18n/LanguageContext';

export type ToastState = {
  message: string;
  type: string;
  /**
   * O-073: Trace-ID des fehlgeschlagenen Serveraufrufs. Nur gesetzt, wenn der
   * Toast wirklich aus einem solchen Aufruf stammt — ein rein clientseitiger
   * Fehler ("kein Platz für ein weiteres Panel") zeigt bewusst keine ID an,
   * weil es zu ihm keine Logzeile gäbe, die der Support finden könnte.
   */
  traceId?: string | null;
};

/**
 * Signatur des Toast-Ausloesers, wie ihn page.tsx bereitstellt. Der dritte
 * Parameter ist der abgefangene Fehler eines Serveraufrufs: aus ihm liest der
 * Toast die Trace-ID (O-073). Weglassen ist ausdruecklich erlaubt -- ein
 * clientseitiger Fehler hat keine.
 */
export type ShowToast = (message: string, type?: string, cause?: unknown) => void;

/**
 * Eigene Komponente statt Inline-Markup in page.tsx, damit die Trace-ID-Zeile
 * testbar ist (page.tsx selbst ist ohne halbe Anwendung nicht renderbar).
 */
export function Toast({ toast, theme }: { toast: ToastState; theme: string }) {
  const { t } = useLanguage();
  const isSuccess = toast.type === 'success';

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 20, scale: 0.95 }}
      role="status"
      className={cn(
        "fixed bottom-4 right-4 z-[100] flex items-start gap-2.5 px-4 py-3 rounded-lg border shadow-2xl backdrop-blur-md text-xs font-semibold tracking-wide transition-colors duration-200",
        isSuccess
          ? (theme === 'dark' ? "bg-ds-emerald-950/90 border-ds-emerald-800/40 text-ds-emerald-300" : "bg-ds-emerald-50/95 border-ds-emerald-200 text-ds-emerald-800")
          : (theme === 'dark' ? "bg-ds-red-950/90 border-ds-red-800/40 text-ds-red-300" : "bg-ds-red-50/95 border-ds-red-200 text-ds-red-800")
      )}
    >
      {isSuccess ? <Check className="w-4 h-4 shrink-0 text-ds-emerald-500" /> : <X className="w-4 h-4 shrink-0 text-ds-red-500" />}
      <div className="flex flex-col gap-1">
        <span>{toast.message}</span>
        {toast.traceId && (
          // select-all: ein Klick markiert die komplette ID, damit sie ohne
          // Abtippen in eine Support-Anfrage wandern kann.
          <span className="select-all font-mono text-[10px] font-normal opacity-80">
            {t('page.toast.traceIdHint', { id: toast.traceId })}
          </span>
        )}
      </div>
    </motion.div>
  );
}
