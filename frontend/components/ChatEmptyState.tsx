"use client";
import type { ShowToast } from './Toast';
import type { ChatMetadata, Project } from '@/types/domain';

import { api } from '@/app/services/api';
import {
  buildEvidenceQuestions,
  buildNormalQuestions,
  detectStacks,
  hasPulseContent,
  pulseTypesToShow,
  shuffle,
  type ProjectPulse,
} from '@/lib/chatStarters';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import {
  AlignLeft,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Code,
  FilePenLine,
  GitBranch,
  History,
  Lightbulb,
  RefreshCw,
  Search,
} from 'lucide-react';
import React from 'react';

type ChatMode = 'normal' | 'evidence';

interface ChatEmptyStateProps {
  theme: string;
  chatMode: ChatMode;
  selectedProject: Project | null;
  onSend: (message: string, extraMetadata?: ChatMetadata) => void;
  onFillMessage: (message: string) => void;
  addAssistantHint: (text: string) => void;
  showToast: ShowToast;
}

interface Scenario {
  id: string;
  tag: string;
  label: string;
  desc: string;
  icon: React.ReactNode;
  /** Was beim Klick in der Eingabe landet — Vorschau auf der Karte. */
  preview: string;
  onSelect: () => void;
  disabled?: boolean;
  disabledTitle?: string;
}

const TYPING_MS_PER_CHAR = 45;
const QUESTION_ROTATION_MS = 9000;
const STATEMENT_POLL_MS = 60000;
const SHIMMER_START_MS = 2500;
const SHIMMER_STEP_MS = 450;

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function focusTextarea() {
  requestAnimationFrame(() => {
    const textarea = document.getElementById('chat-textarea') as HTMLTextAreaElement | null;
    if (!textarea) return;
    textarea.focus();
    const len = textarea.value.length;
    textarea.setSelectionRange(len, len);
  });
}

/**
 * Zähler und Namensstichprobe des Projekts. `settled` wird wahr, sobald das
 * Ergebnis (auch ein Fehlschlag) für das aktuelle Projekt feststeht — vorher
 * soll die Überschrift nicht mit einer allgemeinen Frage anfangen und sie dann
 * sofort wieder verwerfen.
 */
function useProjectPulse(projectId: number | undefined): { pulse: ProjectPulse | null; settled: boolean } {
  const [loaded, setLoaded] = React.useState<{ projectId: number; pulse: ProjectPulse | null } | null>(null);
  React.useEffect(() => {
    if (projectId === undefined) return;
    let cancelled = false;
    (async () => {
      let pulse: ProjectPulse | null = null;
      try {
        const res = await api.getProjectPulse(projectId);
        if (res.data?.counts && res.data?.samples) pulse = res.data;
      } catch {
        // Dekorativ: ohne Pulse fällt die Ansicht auf die allgemeinen Fragen zurück.
      }
      if (!cancelled) setLoaded({ projectId, pulse });
    })();
    return () => { cancelled = true; };
  }, [projectId]);
  // Ein Ergebnis eines früheren Projekts darf nach dem Wechsel nie durchscheinen.
  if (projectId === undefined) return { pulse: null, settled: true };
  const current = loaded && loaded.projectId === projectId ? loaded : null;
  return { pulse: current?.pulse ?? null, settled: current !== null };
}

/**
 * Tippt Fragen zeichenweise in die Überschrift. Mit Projekt-Fragen rotiert die
 * Liste lokal; ohne sie kommt die Frage wie bisher vom Backend (mit lokalem
 * Fallback bei Fehlern).
 */
function useTypedHeadline(questions: string[], t: (key: string) => string, enabled: boolean) {
  const [text, setText] = React.useState('');
  const [isTyping, setIsTyping] = React.useState(false);
  const [nonce, setNonce] = React.useState(0);
  const cursorRef = React.useRef(0);

  React.useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let typingInterval: ReturnType<typeof setInterval> | null = null;

    const startTyping = (statement: string) => {
      if (typingInterval) clearInterval(typingInterval);
      if (prefersReducedMotion()) {
        setText(statement);
        setIsTyping(false);
        return;
      }
      let index = 0;
      setText('');
      setIsTyping(true);
      typingInterval = setInterval(() => {
        if (index < statement.length) {
          // Zeichen vorab greifen: der State-Updater kann von React verzögert
          // ausgeführt werden, wenn `index` schon weitergezählt hat.
          const nextChar = statement.charAt(index);
          setText(prev => prev + nextChar);
          index++;
        } else {
          setIsTyping(false);
          if (typingInterval) clearInterval(typingInterval);
        }
      }, TYPING_MS_PER_CHAR);
    };

    const showNext = async () => {
      if (questions.length > 0) {
        startTyping(questions[cursorRef.current++ % questions.length]);
        return;
      }
      try {
        const res = await api.getTypingStatement();
        if (!cancelled && res.data?.statement) startTyping(res.data.statement);
      } catch (err) {
        console.error('Failed to fetch typing statement', err);
        if (cancelled) return;
        const fallbacks = [
          t('chatView.typingFallbacks.makeCobolKnowledgeVisible'),
          t('chatView.typingFallbacks.navigateMainframeCode'),
          t('chatView.typingFallbacks.unlockLegacySystems'),
          t('chatView.typingFallbacks.programsCopybooksRelations'),
        ];
        startTyping(fallbacks[Math.floor(Math.random() * fallbacks.length)]);
      }
    };

    showNext();
    const rotation = setInterval(showNext, questions.length > 0 ? QUESTION_ROTATION_MS : STATEMENT_POLL_MS);

    return () => {
      cancelled = true;
      if (typingInterval) clearInterval(typingInterval);
      clearInterval(rotation);
    };
  }, [questions, t, nonce, enabled]);

  return { text, isTyping, next: () => setNonce(n => n + 1) };
}

function useCountUp(target: number, durationMs = 700): number {
  const [animated, setAnimated] = React.useState(0);
  const instant = target === 0 || prefersReducedMotion();
  React.useEffect(() => {
    if (instant) return;
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / durationMs);
      setAnimated(Math.round(target * (1 - Math.pow(1 - progress, 3))));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs, instant]);
  return instant ? target : animated;
}

function PulseStat({ value, label, theme }: { value: number; label: string; theme: string }) {
  const shown = useCountUp(value);
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className={cn('tabular-nums font-semibold', theme === 'dark' ? 'text-ds-zinc-200' : 'text-ds-zinc-800')}>
        {shown.toLocaleString()}
      </span>
      <span>{label}</span>
    </span>
  );
}

export function ChatEmptyState({
  theme,
  chatMode,
  selectedProject,
  onSend,
  onFillMessage,
  addAssistantHint,
  showToast,
}: ChatEmptyStateProps) {
  const { t } = useLanguage();
  const isDark = theme === 'dark';
  const isEvidence = chatMode === 'evidence';

  const { pulse, settled } = useProjectPulse(selectedProject?.id);
  const questions = React.useMemo(() => {
    if (isEvidence) return hasPulseContent(pulse) ? shuffle(buildEvidenceQuestions(pulse, t)) : [];
    return shuffle(buildNormalQuestions(pulse, t));
  }, [isEvidence, pulse, t]);
  const { text, isTyping, next } = useTypedHeadline(questions, t, settled);

  // Karten folgen dem stärksten Stack des Projekts (COBOL bleibt Standard).
  const isJava = detectStacks(pulse)[0] === 'java';

  const fill = (message: string) => {
    onFillMessage(message);
    focusTextarea();
  };

  // Karten, die nur ein Thema nennen, stellen die Rückfrage des LLM selbst
  // und legen einen Satzanfang in die Eingabe.
  const clarifyScenario = (id: string, icon: React.ReactNode, key: string): Scenario => {
    const template = t(`chatView.suggestions.${key}.template`);
    return {
      id,
      tag: t(`chatView.empty.tags.${id}`),
      label: t(`chatView.suggestions.${key}.label`),
      desc: t(`chatView.suggestions.${key}.desc`),
      icon,
      preview: template,
      onSelect: () => {
        addAssistantHint(t(`chatView.suggestions.${key}.clarify`));
        fill(template);
      },
    };
  };
  const promptScenario = (id: string, icon: React.ReactNode): Scenario => {
    const prompt = t(`chatView.normalSuggestions.${id}.prompt`);
    return {
      id,
      tag: t(`chatView.empty.tags.${id}`),
      label: t(`chatView.normalSuggestions.${id}.label`),
      desc: t(`chatView.normalSuggestions.${id}.desc`),
      icon,
      preview: prompt,
      onSelect: () => fill(prompt),
    };
  };

  const scenarios: Scenario[] = isEvidence
    ? [
        isJava
          ? clarifyScenario('explainClass', <Code className="w-4 h-4" />, 'explainClass')
          : clarifyScenario('explainProgram', <Code className="w-4 h-4" />, 'explainProgram'),
        isJava
          ? clarifyScenario('traceMethod', <GitBranch className="w-4 h-4" />, 'traceMethod')
          : clarifyScenario('traceCall', <GitBranch className="w-4 h-4" />, 'traceCall'),
        {
          id: 'summarizeDocs',
          tag: t('chatView.empty.tags.summarizeDocs'),
          label: t('chatView.suggestions.summarizeDocs.label'),
          desc: t('chatView.suggestions.summarizeDocs.desc'),
          icon: <History className="w-4 h-4" />,
          preview: t('chatView.suggestions.summarizeDocs.triggerMessage'),
          disabled: !selectedProject,
          disabledTitle: t('chatView.suggestions.summarizeDocs.noProjectTooltip'),
          onSelect: () => {
            if (!selectedProject) {
              showToast(t('chatView.suggestions.summarizeDocs.noProjectToast'), 'error');
              return;
            }
            onSend(t('chatView.suggestions.summarizeDocs.triggerMessage'), { intent: 'onboarding' });
          },
        },
        isJava
          ? clarifyScenario('findProperty', <Search className="w-4 h-4" />, 'findProperty')
          : clarifyScenario('findField', <Search className="w-4 h-4" />, 'findField'),
      ]
    : [
        promptScenario('explainConcept', <BookOpen className="w-4 h-4" />),
        promptScenario('draftText', <FilePenLine className="w-4 h-4" />),
        promptScenario('summarizeText', <AlignLeft className="w-4 h-4" />),
        promptScenario('brainstorm', <Lightbulb className="w-4 h-4" />),
      ];

  const stats = isEvidence && hasPulseContent(pulse) ? pulse : null;

  return (
    <div className="flex-1 flex flex-col items-center justify-start text-center gap-5 @3xl/chat:gap-6 pt-2 pb-4 relative">
      {/* Zeilenraster als ruhiger Hintergrund; nutzt die Theme-Variablen, kein Glow. */}
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-[300px] pointer-events-none z-0"
        style={{
          backgroundImage:
            'linear-gradient(to right, rgb(var(--ds-border) / 0.22) 1px, transparent 1px), linear-gradient(to bottom, rgb(var(--ds-border) / 0.22) 1px, transparent 1px)',
          backgroundSize: '32px 32px',
          maskImage: 'radial-gradient(ellipse 65% 60% at 50% 25%, black 10%, transparent 75%)',
          WebkitMaskImage: 'radial-gradient(ellipse 65% 60% at 50% 25%, black 10%, transparent 75%)',
        }}
      />

      <div className="relative z-10 w-full max-w-3xl space-y-3">
        <div
          key={chatMode}
          className="inline-flex items-center gap-2 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-ds-zinc-500 animate-in fade-in slide-in-from-bottom-1 duration-200 motion-reduce:animate-none"
        >
          <span className="relative flex h-1.5 w-1.5">
            {isEvidence && (
              <span className="absolute inset-0 rounded-full bg-ds-indigo-500 animate-ds-dot-pulse motion-reduce:animate-none" />
            )}
            <span className={cn('relative h-1.5 w-1.5 rounded-full', isEvidence ? 'bg-ds-indigo-500' : 'bg-ds-zinc-500')} />
          </span>
          {t(`chatView.empty.kicker.${chatMode}`)}
        </div>

        <h1 className={cn(
          'text-3xl @md/chat:text-4xl font-heading font-extrabold tracking-tight leading-tight text-center min-h-[2.2em] flex items-start justify-center',
          isDark ? 'text-ds-white' : 'text-ds-zinc-900'
        )}>
          <span className="inline-flex items-center justify-center gap-2.5 flex-wrap">
            <span>
              {text}
              <span
                aria-hidden="true"
                className={cn(
                  'ml-1 inline-block h-[0.85em] w-[3px] translate-y-[0.1em] bg-ds-indigo-500',
                  isTyping ? 'opacity-100' : 'animate-ds-caret motion-reduce:animate-none'
                )}
              />
            </span>
            {!isTyping && text && (
              <span className="inline-flex items-center gap-1.5 shrink-0 animate-in fade-in duration-200 motion-reduce:animate-none">
                <button
                  type="button"
                  onClick={next}
                  className={cn(
                    'group inline-flex items-center justify-center p-1.5 rounded-lg border transition-colors duration-150',
                    isDark
                      ? 'bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-400 hover:text-ds-zinc-200 hover:border-ds-zinc-700'
                      : 'bg-ds-white border-ds-zinc-200 text-ds-zinc-500 hover:text-ds-zinc-800 hover:border-ds-zinc-300'
                  )}
                  title={t('chatView.empty.shuffleTitle')}
                  aria-label={t('chatView.empty.shuffleTitle')}
                >
                  <RefreshCw className="w-4 h-4 transition-transform duration-300 group-hover:rotate-180 motion-reduce:transition-none" />
                </button>
                <button
                  type="button"
                  onClick={() => onSend(text)}
                  className={cn(
                    'group inline-flex items-center justify-center p-1.5 rounded-lg border transition-colors duration-150',
                    isDark
                      ? 'bg-ds-zinc-900 border-ds-zinc-800 text-ds-indigo-400 hover:text-ds-indigo-350 hover:border-ds-zinc-700'
                      : 'bg-ds-white border-ds-zinc-200 text-ds-indigo-650 hover:text-ds-indigo-700 hover:border-ds-zinc-300'
                  )}
                  title={t('chatView.askDirectlyTitle')}
                  aria-label={t('chatView.askDirectlyTitle')}
                >
                  <ArrowRight className="w-4 h-4 transition-transform duration-150 group-hover:translate-x-0.5 motion-reduce:transition-none" />
                </button>
              </span>
            )}
          </span>
        </h1>

        {/* Nur im Evidenz-Modus: die Spur zieht sich unter der Frage auf, wie eine Quellenmarke. */}
        {isEvidence && (
          <div aria-hidden="true" className="mx-auto flex w-40 items-center" key={`trace-${chatMode}`}>
            <span className="h-px flex-1 origin-left bg-ds-indigo-500/60 animate-ds-trace motion-reduce:animate-none" />
            <span
              className="h-1.5 w-1.5 bg-ds-indigo-500 animate-in fade-in duration-300 motion-reduce:animate-none"
              style={{ animationDelay: '500ms', animationFillMode: 'backwards' }}
            />
          </div>
        )}

        {stats && (
          <div
            className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-[0.14em] text-ds-zinc-500 animate-in fade-in duration-300 motion-reduce:animate-none"
            aria-label={selectedProject?.name}
          >
            {pulseTypesToShow(stats).map(type => (
              <PulseStat key={type} value={stats.counts[type]} label={t(`chatView.empty.counts.${type}`)} theme={theme} />
            ))}
          </div>
        )}
      </div>

      {/* Szenario-Karten: neu aufgebaut beim Moduswechsel, damit der Wechsel sichtbar wird. */}
      <div key={chatMode} className="grid grid-cols-1 @lg/chat:grid-cols-2 @4xl/chat:grid-cols-4 gap-3 w-full max-w-6xl relative z-10">
        {scenarios.map((scenario, idx) => {
          const interactive = !scenario.disabled;
          return (
            <button
              type="button"
              key={scenario.id}
              id={`chat-hint-button-${idx}`}
              disabled={scenario.disabled}
              title={scenario.disabled ? scenario.disabledTitle : undefined}
              onClick={scenario.onSelect}
              style={{ animationDelay: `${idx * 70}ms`, animationFillMode: 'backwards' }}
              className={cn(
                'group relative overflow-hidden rounded-lg border text-left transition-colors duration-150 animate-in fade-in slide-in-from-bottom-2 duration-300 motion-reduce:animate-none',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ds-indigo-500',
                scenario.disabled && 'opacity-50 cursor-not-allowed',
                isDark
                  ? 'bg-ds-zinc-900/60 border-ds-zinc-800 text-ds-zinc-200'
                  : 'bg-ds-white border-ds-zinc-200 text-ds-zinc-800',
                interactive && (isDark ? 'hover:bg-ds-zinc-900 hover:border-ds-zinc-700' : 'hover:bg-ds-zinc-50 hover:border-ds-zinc-300')
              )}
            >
              {/* Periodischer Schimmer: läuft nacheinander über alle Karten, dann lange Ruhe. */}
              <span
                aria-hidden="true"
                className="ds-card-shimmer pointer-events-none absolute inset-0 z-0 overflow-hidden rounded-lg motion-reduce:hidden"
                style={{ '--ds-shimmer-delay': `${SHIMMER_START_MS + idx * SHIMMER_STEP_MS}ms` } as React.CSSProperties}
              >
                <span className="ds-card-shimmer-ring absolute inset-0 rounded-lg border border-ds-indigo-500/70" />
                <span className="ds-card-shimmer-sweep absolute inset-y-0 left-0 w-1/2 bg-gradient-to-r from-transparent via-ds-indigo-500/15 to-transparent" />
              </span>
              {/* Signalmarke links, wie in der Navigation */}
              {interactive && (
                <span
                  aria-hidden="true"
                  className="absolute inset-y-0 left-0 w-0.5 origin-top scale-y-0 bg-ds-indigo-500 transition-transform duration-150 group-hover:scale-y-100 group-focus-visible:scale-y-100 motion-reduce:transition-none"
                />
              )}
              <div className="relative z-10 flex flex-col gap-2.5 p-4">
                <div className="flex items-center justify-between font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-ds-zinc-500">
                  <span>{String(idx + 1).padStart(2, '0')} · {scenario.tag}</span>
                  {interactive && (
                    <ArrowUpRight className="w-3.5 h-3.5 -translate-x-1 translate-y-1 opacity-0 transition duration-150 group-hover:translate-x-0 group-hover:translate-y-0 group-hover:opacity-100 group-focus-visible:translate-x-0 group-focus-visible:translate-y-0 group-focus-visible:opacity-100 motion-reduce:transition-none" />
                  )}
                </div>
                <div className="flex items-start gap-3">
                  <div className={cn(
                    'mt-0.5 shrink-0 rounded-md border p-2 transition-colors duration-150',
                    isDark ? 'bg-ds-zinc-950 border-ds-zinc-800 text-ds-zinc-400' : 'bg-ds-zinc-50 border-ds-zinc-200 text-ds-zinc-500',
                    interactive && 'group-hover:text-ds-indigo-500 group-focus-visible:text-ds-indigo-500'
                  )}>
                    {scenario.icon}
                  </div>
                  <div className="space-y-0.5">
                    <span className="block text-sm font-bold">{scenario.label}</span>
                    <span className="block text-xs text-ds-zinc-500 leading-snug">{scenario.desc}</span>
                  </div>
                </div>
                {/* Vorschau des Eintrags: Platz ist reserviert (kein Layout-Sprung), Hover/Fokus schärft sie nur. */}
                <div
                  aria-hidden="true"
                  className={cn(
                    'flex items-center gap-1.5 rounded border px-2.5 py-1.5 font-mono text-[11px] opacity-60 transition-opacity duration-150 motion-reduce:transition-none',
                    interactive && 'group-hover:opacity-100 group-focus-visible:opacity-100',
                    isDark ? 'border-ds-zinc-800 bg-ds-zinc-950 text-ds-zinc-400' : 'border-ds-zinc-200 bg-ds-zinc-50 text-ds-zinc-600'
                  )}
                >
                  <span className="text-ds-indigo-500">›</span>
                  <span className="truncate whitespace-pre">{scenario.preview}</span>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
