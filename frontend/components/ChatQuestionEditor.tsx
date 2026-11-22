"use client";
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { useEffect, useRef, useState } from 'react';

/**
 * Bearbeiten der letzten Frage direkt in ihrer Blase: Enter sendet, Umschalt+Enter bricht um, Esc verwirft.
 * Senden ersetzt Frage und Antwort; frühere Fassungen der Antwort bleiben erhalten.
 */
export function ChatQuestionEditor({ initial, theme, onCancel, onSubmit }: {
  initial: string;
  theme: string;
  onCancel: () => void;
  onSubmit: (text: string) => void;
}) {
  const { t } = useLanguage();
  const [text, setText] = useState(initial);
  const field = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const element = field.current;
    if (!element) return;
    element.focus();
    element.setSelectionRange(element.value.length, element.value.length);
    element.style.height = `${Math.min(element.scrollHeight, 240)}px`;
  }, []);
  const submit = () => { if (text.trim()) onSubmit(text.trim()); };
  return (
    <div className="space-y-2">
      <textarea
        ref={field}
        value={text}
        aria-label={t('chatView.editQuestion')}
        rows={1}
        onChange={(event) => {
          setText(event.target.value);
          event.target.style.height = 'auto';
          event.target.style.height = `${Math.min(event.target.scrollHeight, 240)}px`;
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(); }
          if (event.key === 'Escape') { event.preventDefault(); onCancel(); }
        }}
        className={cn(
          "w-full min-w-[min(28rem,60vw)] resize-none rounded-md border px-2.5 py-1.5 font-medium leading-relaxed outline-none transition-colors",
          theme === 'dark'
            ? "border-ds-zinc-700/70 bg-ds-zinc-950/40 focus:border-ds-indigo-500/60"
            : "border-ds-zinc-200 bg-ds-zinc-50 focus:border-ds-indigo-500/60",
        )}
      />
      <div className="flex justify-end gap-1.5">
        <Button variant="ghost" size="sm" onClick={onCancel}
          className={cn("h-7 px-3 text-xs", theme === 'dark' ? "text-ds-zinc-400 hover:bg-ds-zinc-800" : "text-ds-zinc-600 hover:bg-ds-zinc-100")}>
          {t('common.cancel')}
        </Button>
        <Button size="sm" onClick={submit} disabled={!text.trim()}
          className="h-7 px-3 text-xs bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-500">
          {t('chatView.resend')}
        </Button>
      </div>
    </div>
  );
}
