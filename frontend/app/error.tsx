'use client';

import { useState } from 'react';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { API_URL } from '@/app/services/api';

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useLanguage();
  const [reportState, setReportState] = useState<'idle' | 'sending' | 'sent' | 'failed'>('idle');

  // Opt-in only — never sent automatically. A crash report is meant to help
  // us fix the bug, not to phone home on every error a user hits.
  const sendReport = async () => {
    setReportState('sending');
    try {
      await fetch(`${API_URL}/diagnostics/client-error`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: error.message,
          stack: error.stack,
          digest: error.digest,
          url: typeof window !== 'undefined' ? window.location.href : undefined,
        }),
      });
      setReportState('sent');
    } catch {
      setReportState('failed');
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 p-6">
      <div className="max-w-md w-full space-y-4 rounded-lg border border-zinc-800 bg-zinc-900 p-6 text-center">
        <h1 className="text-lg font-bold text-zinc-100">{t('errorBoundary.title')}</h1>
        <p className="text-sm text-zinc-400">{t('errorBoundary.description')}</p>
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            onClick={reset}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
          >
            {t('errorBoundary.resetButton')}
          </button>
          <button
            onClick={sendReport}
            disabled={reportState === 'sending' || reportState === 'sent'}
            className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm font-semibold text-zinc-200 hover:bg-zinc-700 disabled:opacity-60"
          >
            {reportState === 'sending' ? t('errorBoundary.sendingReportButton') : t('errorBoundary.sendReportButton')}
          </button>
        </div>
        {reportState === 'sent' && (
          <p className="text-xs text-emerald-400">{t('errorBoundary.reportSentToast')}</p>
        )}
        {reportState === 'failed' && (
          <p className="text-xs text-rose-400">{t('errorBoundary.reportFailedToast')}</p>
        )}
      </div>
    </div>
  );
}
