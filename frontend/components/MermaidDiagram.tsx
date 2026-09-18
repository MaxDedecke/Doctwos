"use client";

import { sanitizeSvg } from '@/lib/sanitize';
import { cn } from '@/lib/utils';
import { AlertTriangle, Loader2, Maximize2, X } from 'lucide-react';
import React, { useEffect, useId, useState } from 'react';

interface MermaidDiagramProps {
  code: string;
  theme: string;
}

interface MermaidSvgProps extends MermaidDiagramProps {
  expanded?: boolean;
}

/** Render Mermaid supplied by an agent answer without trusting its SVG output. */
function MermaidSvg({ code, theme, expanded = false }: MermaidSvgProps) {
  const reactId = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const [svg, setSvg] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const { default: mermaid } = await import('mermaid');
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          theme: theme === 'dark' ? 'dark' : 'default',
          fontFamily: 'Archivo, Arial, sans-serif',
          flowchart: { htmlLabels: false },
        });
        const result = await mermaid.render(`doctus-mermaid-${reactId}`, code);
        if (!cancelled) setSvg(sanitizeSvg(result.svg));
      } catch {
        if (!cancelled) setError('Das Ablaufdiagramm konnte nicht gerendert werden.');
      }
    })();

    return () => { cancelled = true; };
  }, [code, reactId, theme]);

  if (error) {
    return (
      <div className={cn('my-4 flex items-center gap-2 rounded-lg border px-3 py-2 text-sm', theme === 'dark' ? 'border-ds-amber-500/30 bg-ds-amber-500/10 text-ds-amber-300' : 'border-ds-amber-500/40 bg-ds-amber-50 text-ds-amber-700')}>
        <AlertTriangle className="h-4 w-4 shrink-0" />{error}
      </div>
    );
  }

  return (
    <div className={cn(expanded ? 'flex h-full min-h-0 items-center justify-center overflow-auto' : 'min-h-16 overflow-x-auto')}>
      {svg ? <div className={cn(expanded ? 'h-full w-full [&>svg]:h-full [&>svg]:w-full' : 'min-w-max')} dangerouslySetInnerHTML={{ __html: svg }} /> : <div className="flex min-h-16 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-ds-indigo-500" /></div>}
    </div>
  );
}

/** A compact chat diagram with a large, distraction-free inspection dialog. */
export function MermaidDiagram({ code, theme }: MermaidDiagramProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    if (!isExpanded) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsExpanded(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [isExpanded]);

  const isDark = theme === 'dark';
  return (
    <>
      <div className={cn('relative my-4 min-h-24 overflow-x-auto rounded-lg border p-4', isDark ? 'border-ds-zinc-800 bg-ds-zinc-950/80' : 'border-ds-zinc-200 bg-ds-zinc-50')}>
        <button
          type="button"
          onClick={() => setIsExpanded(true)}
          aria-label="Diagramm maximieren"
          title="Diagramm maximieren"
          className={cn('absolute right-2 top-2 z-10 rounded border p-1.5 shadow-sm transition-colors', isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-300 hover:text-ds-indigo-400' : 'border-ds-zinc-200 bg-ds-white text-ds-zinc-600 hover:text-ds-indigo-600')}
        >
          <Maximize2 className="h-4 w-4" />
        </button>
        <MermaidSvg code={code} theme={theme} />
      </div>

      {isExpanded && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Ablaufdiagramm in Großansicht"
          className="fixed inset-0 z-[120] flex items-center justify-center bg-ds-black/80 p-3 backdrop-blur-sm sm:p-6"
          onMouseDown={(event) => { if (event.target === event.currentTarget) setIsExpanded(false); }}
        >
          <section className={cn('flex h-[calc(100dvh-1.5rem)] w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-xl border shadow-2xl sm:h-[calc(100dvh-3rem)] sm:w-[calc(100vw-3rem)]', isDark ? 'border-ds-zinc-700 bg-ds-zinc-950 text-ds-zinc-100' : 'border-ds-zinc-200 bg-ds-white text-ds-zinc-900')}>
            <header className={cn('flex shrink-0 items-center justify-between border-b px-4 py-3', isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200')}>
              <h2 className="text-sm font-semibold">Ablaufdiagramm</h2>
              <button
                type="button"
                onClick={() => setIsExpanded(false)}
                aria-label="Großansicht schließen"
                title="Schließen (Esc)"
                className={cn('rounded p-1.5 transition-colors', isDark ? 'text-ds-zinc-400 hover:bg-ds-zinc-800 hover:text-ds-zinc-100' : 'text-ds-zinc-500 hover:bg-ds-zinc-100 hover:text-ds-zinc-900')}
              >
                <X className="h-5 w-5" />
              </button>
            </header>
            <div className={cn('min-h-0 flex-1 p-4 sm:p-6', isDark ? 'bg-ds-zinc-950' : 'bg-ds-zinc-50')}>
              <MermaidSvg code={code} theme={theme} expanded />
            </div>
          </section>
        </div>
      )}
    </>
  );
}
