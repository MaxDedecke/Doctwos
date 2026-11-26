"use client";
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from "@/lib/utils";
import React, { useEffect, useState } from 'react';
import { CodenaLogo } from './Logo';

type Token = { k: string } | { w: number };
type Line = { indent: number; tokens: Token[] };

// Bewusst ohne Programm- oder Feldnamen: Schlüsselwörter sind echt, Operanden nur Balken.
const FIRST_LINE = 118;
const CODE: Line[] = [
  { indent: 0, tokens: [{ k: 'PROCEDURE DIVISION.' }] },
  { indent: 1, tokens: [{ k: 'PERFORM' }, { w: 9 }] },
  { indent: 1, tokens: [{ k: 'IF' }, { w: 6 }, { k: '=' }, { w: 3 }] },
  { indent: 2, tokens: [{ k: 'MOVE' }, { w: 7 }, { k: 'TO' }, { w: 8 }] },
  { indent: 2, tokens: [{ k: 'CALL' }, { w: 8 }, { k: 'USING' }, { w: 6 }] },
  { indent: 1, tokens: [{ k: 'ELSE' }] },
  { indent: 2, tokens: [{ k: 'PERFORM' }, { w: 11 }] },
  { indent: 1, tokens: [{ k: 'END-IF' }] },
  { indent: 1, tokens: [{ k: 'READ' }, { w: 7 }, { k: 'INTO' }, { w: 7 }] },
  { indent: 1, tokens: [{ k: 'GOBACK.' }] },
];
const CITED = [1, 4, 8];
const ANSWER_WIDTHS = [[78, 46], [64, 70], [84, 38]];
const STEP_MS = 2600;

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** Belegspur: die zitierte Codezeile und ihr Beleg in der Antwort leuchten gemeinsam auf. */
function EvidenceTrace({ active }: { active: number }) {
  const { t } = useLanguage();
  const activeLine = CITED[active];
  return (
    <div aria-hidden="true" className="relative select-none pr-10 pb-16">
      <div className="border border-[rgb(var(--bp-faint)/0.12)] bg-[rgb(var(--bp-surface))] rounded-md overflow-hidden">
        <div className="flex items-center gap-2 px-4 h-9 border-b border-[rgb(var(--bp-faint)/0.1)]">
          <span className="font-mono text-[0.6875rem] text-[rgb(var(--bp-trace))]">&gt;_</span>
          <span className="h-1.5 w-16 rounded-full bg-[rgb(var(--bp-faint)/0.18)]" />
          <span className="font-mono text-[0.6875rem] text-[rgb(var(--bp-muted))]">.cbl</span>
        </div>
        <div className="py-2 font-mono text-[0.75rem] leading-[1.6rem]">
          {CODE.map((line, i) => {
            const cited = CITED.includes(i);
            const isActive = i === activeLine;
            return (
              <div
                key={i}
                className={cn(
                  "relative flex items-center pr-4 transition-colors duration-150",
                  isActive && "bg-[rgb(var(--bp-trace)/0.12)]",
                )}
              >
                <span className={cn(
                  "absolute left-0 top-0 bottom-0 w-[3px] transition-opacity duration-150",
                  isActive ? "codena-brand-gradient opacity-100" : cited ? "bg-[rgb(var(--bp-trace)/0.35)] opacity-100" : "opacity-0",
                )} />
                <span className={cn(
                  "w-12 shrink-0 text-right pr-4 tabular-nums",
                  isActive ? "text-[rgb(var(--bp-trace))]" : "text-[rgb(var(--bp-muted)/0.55)]",
                )}>
                  {FIRST_LINE + i}
                </span>
                <span className="flex items-center gap-2" style={{ paddingLeft: `${line.indent * 1.5}rem` }}>
                  {line.tokens.map((tok, k) => 'k' in tok
                    ? <span key={k} className="text-[rgb(var(--bp-trace)/0.9)]">{tok.k}</span>
                    : <span key={k} className="h-[0.45rem] rounded-full bg-[rgb(var(--bp-faint)/0.2)]" style={{ width: `${tok.w * 0.5}rem` }} />)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="absolute right-0 bottom-0 w-[62%] border border-[rgb(var(--bp-faint)/0.16)] bg-[#0b1210] rounded-md p-4 shadow-[8px_8px_0_rgb(0_0_0/0.35)]">
        <div className="codena-kicker text-[rgb(var(--bp-muted))] flex items-center gap-2">
          <span className="h-1.5 w-1.5 codena-brand-gradient" />
          {t('loginView.brandAnswer')}
        </div>
        <div className="mt-3 space-y-2.5">
          {CITED.map((lineIdx, i) => (
            <div key={lineIdx} className="flex items-center gap-2">
              <span className="h-1.5 rounded-full bg-[rgb(var(--bp-faint)/0.22)]" style={{ width: `${ANSWER_WIDTHS[i][0]}%` }} />
              <span className={cn(
                "shrink-0 font-mono text-[0.625rem] px-1.5 py-0.5 rounded-sm border transition-colors duration-150",
                i === active
                  ? "codena-brand-gradient border-transparent text-white"
                  : "border-[rgb(var(--bp-trace)/0.4)] text-[rgb(var(--bp-trace))]",
              )}>
                .cbl:{FIRST_LINE + lineIdx}
              </span>
            </div>
          ))}
          <span className="block h-1.5 rounded-full bg-[rgb(var(--bp-faint)/0.12)]" style={{ width: '52%' }} />
        </div>
      </div>
    </div>
  );
}

export function LoginBrandPanel({ className }: { className?: string }) {
  const { t } = useLanguage();
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (prefersReducedMotion()) return;
    const id = window.setInterval(() => setActive((a) => (a + 1) % CITED.length), STEP_MS);
    return () => window.clearInterval(id);
  }, []);

  return (
    <aside className={cn("codena-brand-panel relative flex-col justify-between overflow-hidden border-r border-[rgb(236_238_232/0.08)] px-12 py-12 xl:px-16 xl:py-14", className)}>
      <CodenaLogo className="relative text-[2.4rem] self-start" />

      <div className="relative max-w-[38rem] space-y-10">
        <div className="space-y-5">
          <div className="codena-kicker text-[rgb(var(--bp-muted))] flex items-center gap-2">
            <span className="h-1.5 w-1.5 codena-brand-gradient" />
            {t('loginView.brandEyebrow')}
          </div>
          <h1 className="font-heading font-semibold text-[2.5rem] xl:text-[2.9rem] leading-[1.04] tracking-[-0.035em]">
            {t('loginView.brandTitle')}
            <span className="block text-[rgb(var(--bp-trace))]">{t('loginView.brandTitleAccent')}</span>
          </h1>
          <p className="text-[0.95rem] leading-relaxed text-[rgb(var(--bp-muted))] max-w-[30rem]">
            {t('loginView.brandLead')}
          </p>
        </div>
        <div className="[@media(max-height:820px)]:hidden">
          <EvidenceTrace active={active} />
        </div>
      </div>

      <div className="relative flex flex-wrap gap-x-8 gap-y-2 border-t border-[rgb(236_238_232/0.1)] pt-5 codena-kicker text-[rgb(var(--bp-muted))]">
        <span>{t('loginView.brandFactOnPrem')}</span>
        <span>{t('loginView.brandFactLanguages')}</span>
        <span>{t('loginView.brandFactEvidence')}</span>
      </div>
    </aside>
  );
}
