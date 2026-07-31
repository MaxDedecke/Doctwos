'use client';

import { useState } from 'react';
import { API_URL } from '@/app/services/api';

// Only fires if the ROOT layout itself throws — must render its own
// <html>/<body> since the crashed layout (and everything inside it,
// including LanguageProvider) is gone. Plain English only, no i18n context
// available here.
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const [reportState, setReportState] = useState<'idle' | 'sending' | 'sent' | 'failed'>('idle');

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
    <html>
      <body style={{ margin: 0 }}>
        <div style={{
          display: 'flex', minHeight: '100vh', alignItems: 'center', justifyContent: 'center',
          backgroundColor: '#09090b', padding: '24px', fontFamily: 'sans-serif',
        }}>
          <div style={{
            maxWidth: '28rem', width: '100%', textAlign: 'center',
            borderRadius: '12px', border: '1px solid #27272a', backgroundColor: '#18181b',
            padding: '24px',
          }}>
            <h1 style={{ fontSize: '18px', fontWeight: 700, color: '#f4f4f5' }}>Something went wrong</h1>
            <p style={{ fontSize: '14px', color: '#a1a1aa', marginTop: '8px' }}>
              An unexpected error occurred. You can try again, or send an anonymous error report to help us fix it.
            </p>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', marginTop: '16px' }}>
              <button
                onClick={reset}
                style={{
                  borderRadius: '8px', backgroundColor: '#4d7fff', color: 'white',
                  padding: '8px 16px', fontSize: '14px', fontWeight: 600, border: 'none', cursor: 'pointer',
                }}
              >
                Try again
              </button>
              <button
                onClick={sendReport}
                disabled={reportState === 'sending' || reportState === 'sent'}
                style={{
                  borderRadius: '8px', border: '1px solid #3f3f46', backgroundColor: '#27272a', color: '#e4e4e7',
                  padding: '8px 16px', fontSize: '14px', fontWeight: 600, cursor: 'pointer',
                  opacity: reportState === 'sending' || reportState === 'sent' ? 0.6 : 1,
                }}
              >
                {reportState === 'sending' ? 'Sending...' : 'Send error report'}
              </button>
            </div>
            {reportState === 'sent' && (
              <p style={{ fontSize: '12px', color: '#34d399', marginTop: '8px' }}>Error report sent, thank you</p>
            )}
            {reportState === 'failed' && (
              <p style={{ fontSize: '12px', color: '#fb7185', marginTop: '8px' }}>Failed to send error report</p>
            )}
          </div>
        </div>
      </body>
    </html>
  );
}
