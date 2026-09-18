"use client";

import { sanitizeSvg } from '@/lib/sanitize';
import { cn } from '@/lib/utils';
import { AlertTriangle, Loader2 } from 'lucide-react';
import React, { useEffect, useId, useState } from 'react';

interface MermaidDiagramProps {
  code: string;
  theme: string;
}

/** Render Mermaid supplied by an agent answer without trusting its SVG output. */
export function MermaidDiagram({ code, theme }: MermaidDiagramProps) {
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
    <div className={cn('my-4 min-h-24 overflow-x-auto rounded-lg border p-4', theme === 'dark' ? 'border-ds-zinc-800 bg-ds-zinc-950/80' : 'border-ds-zinc-200 bg-ds-zinc-50')}>
      {svg ? <div className="min-w-max" dangerouslySetInnerHTML={{ __html: svg }} /> : <div className="flex min-h-16 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-ds-indigo-500" /></div>}
    </div>
  );
}
