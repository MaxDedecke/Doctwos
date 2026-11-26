"use client";
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from "@/lib/utils";
import React, { useEffect, useState } from 'react';
import { CodenaLogo, CodenaMark } from './Logo';

const QUESTION_KEYS = ['q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7'];
// Gleiches Tempo wie die getippte Überschrift im leeren Chat (ChatEmptyState).
const TYPING_MS_PER_CHAR = 45;
const HOLD_MS = 3800;

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** Tippt die Fragen nacheinander; nach jeder Frage blinkt der Cursor, dann folgt die nächste. */
function useRotatingQuestion(questions: string[]) {
  const [text, setText] = useState('');
  const [isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    if (prefersReducedMotion()) {
      queueMicrotask(() => setText(questions[0] ?? ''));
      return;
    }
    let index = 0;
    let typing: ReturnType<typeof setInterval> | null = null;
    let hold: ReturnType<typeof setTimeout> | null = null;

    const type = () => {
      const statement = questions[index++ % questions.length];
      let pos = 0;
      setText('');
      setIsTyping(true);
      typing = setInterval(() => {
        pos++;
        setText(statement.slice(0, pos));
        if (pos >= statement.length) {
          if (typing) clearInterval(typing);
          setIsTyping(false);
          hold = setTimeout(type, HOLD_MS);
        }
      }, TYPING_MS_PER_CHAR);
    };
    type();

    return () => {
      if (typing) clearInterval(typing);
      if (hold) clearTimeout(hold);
    };
  }, [questions]);

  return { text, isTyping };
}

export function LoginBrandPanel({ className }: { className?: string }) {
  const { t } = useLanguage();
  const questions = React.useMemo(
    () => QUESTION_KEYS.map((k) => t(`loginView.brandQuestions.${k}`)),
    [t],
  );
  const { text, isTyping } = useRotatingQuestion(questions);

  return (
    <aside
      aria-hidden="true"
      className={cn("codena-brand-panel relative items-center overflow-hidden border-r border-[rgb(236_238_232/0.08)] px-12 xl:px-20 select-none", className)}
    >
      <CodenaMark className="pointer-events-none absolute -right-[18%] -bottom-[22%] !w-[62%] !h-auto opacity-[0.05]" />

      <div className="relative">
      <CodenaLogo className="text-[2.6rem] mb-10" />
      <p className="relative max-w-[36rem] min-h-[3.3em] font-heading font-semibold text-[2.6rem] xl:text-[3rem] leading-[1.1] tracking-[-0.035em]">
        {text}
        <span
          className={cn(
            'ml-1.5 inline-block h-[0.85em] w-[4px] translate-y-[0.1em] bg-[rgb(var(--bp-trace))]',
            isTyping ? 'opacity-100' : 'animate-ds-caret motion-reduce:animate-none',
          )}
        />
      </p>
      </div>
    </aside>
  );
}
