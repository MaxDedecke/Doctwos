"use client";
import type { FeedbackReason } from '@/types/domain';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { useState } from 'react';

const REASONS: FeedbackReason[] = ['wrong_source', 'incorrect', 'incomplete', 'not_helpful', 'too_long', 'other'];

/** Nach einem Daumen runter: Was war falsch? Ein Grund ist freiwillig, hilft aber der Auswertung. */
export function FeedbackReasonPicker({ theme, onSubmit, onClose }: {
  theme: string;
  onSubmit: (reason?: FeedbackReason, comment?: string) => void;
  onClose: () => void;
}) {
  const { t } = useLanguage();
  const [reason, setReason] = useState<FeedbackReason | null>(null);
  const [comment, setComment] = useState('');
  return (
    <div role="dialog" aria-label={t('chatView.feedbackReason.title')} className={cn(
      'mt-2 w-full max-w-md rounded-lg border p-2.5 text-xs space-y-2',
      theme === 'dark' ? 'bg-ds-zinc-900 border-ds-zinc-800' : 'bg-ds-white border-ds-zinc-200',
    )}>
      <div className="font-semibold">{t('chatView.feedbackReason.title')}</div>
      <div className="flex flex-wrap gap-1.5">
        {REASONS.map(option => (
          <button key={option} type="button" aria-pressed={reason === option} onClick={() => setReason(option)}
            className={cn('rounded-full border px-2 py-0.5', reason === option
              ? 'border-ds-red-500 bg-ds-red-500/10 text-ds-red-500'
              : 'border-ds-zinc-500/30 text-ds-zinc-500 hover:border-ds-zinc-400')}>
            {t(`chatView.feedbackReason.${option}`)}
          </button>
        ))}
      </div>
      <textarea value={comment} onChange={event => setComment(event.target.value.slice(0, 500))} rows={2}
        placeholder={t('chatView.feedbackReason.commentPlaceholder')} aria-label={t('chatView.feedbackReason.commentPlaceholder')}
        className="w-full rounded border border-ds-zinc-500/30 bg-transparent p-1.5" />
      <div className="flex justify-end gap-1.5">
        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={onClose}>{t('chatView.feedbackReason.skip')}</Button>
        <Button size="sm" className="h-7 text-xs" disabled={!reason && !comment.trim()}
          onClick={() => onSubmit(reason ?? 'other', comment.trim() || undefined)}>{t('chatView.feedbackReason.send')}</Button>
      </div>
    </div>
  );
}
