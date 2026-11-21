import { highlightLines, TOKEN_CLASS, type HighlightLanguage } from '@/lib/codeHighlight';
import { cn } from '@/lib/utils';
import React from 'react';

/** Codezeilen mit Hervorhebung; ohne bekannte Sprache unverändert. `firstLine` schaltet Zeilennummern ein. */
export function HighlightedCode({ code, language, firstLine, markLine }: {
  code: string;
  language: HighlightLanguage | null;
  firstLine?: number;
  /** Zeilennummer, die hinterlegt wird (die zitierte Zeile). */
  markLine?: number;
}) {
  const lines = language ? highlightLines(code, language) : code.split('\n').map(text => [{ text, kind: 'text' as const }]);
  return (
    <>
      {lines.map((tokens, index) => {
        const number = firstLine != null ? firstLine + index : null;
        const content = tokens.length
          ? tokens.map((token, position) => (
            <span key={position} className={TOKEN_CLASS[token.kind] || undefined}>{token.text}</span>
          ))
          : (number == null ? '' : ' ');
        if (number == null) return <React.Fragment key={index}>{content}{index < lines.length - 1 ? '\n' : ''}</React.Fragment>;
        return (
          <span key={index} className={cn('grid grid-cols-[2.5rem_minmax(0,1fr)] gap-3', number === markLine && 'bg-ds-indigo-500/10')}>
            <span aria-hidden="true" className="select-none text-right text-ds-zinc-500/70">{number}</span>
            <span>{content}</span>
          </span>
        );
      })}
    </>
  );
}
