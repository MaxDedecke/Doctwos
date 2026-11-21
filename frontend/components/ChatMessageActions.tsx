"use client";
import type { ShowToast } from './Toast';
import type { ChatMessage, FeedbackReason, Project } from '@/types/domain';
import { FeedbackReasonPicker } from '@/components/FeedbackReasonPicker';
import { useState } from 'react';
import { InsightDraftAction } from '@/components/InsightDraftAction';
import { chatInsightEvidence } from '@/lib/chatInsightEvidence';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { hasCompactableCitation } from '@/lib/citationLabel';
import { cn, copyToClipboard } from '@/lib/utils';
import { ChevronLeft, ChevronRight, Copy, Cpu, FolderTree, RotateCcw, ThumbsDown, ThumbsUp } from 'lucide-react';

interface ChatMessageActionsProps {
  message: ChatMessage;
  index: number;
  theme: string;
  isLoading: boolean;
  showOriginal: boolean;
  onToggleOriginal: () => void;
  onFeedback: (messageId: number, feedback: 'up' | 'down', reason?: FeedbackReason, comment?: string) => void;
  /** Angezeigte Fassung (Index in versions, bei versionCount die aktuelle) und Wechsel dorthin. */
  versionIndex: number;
  onVersionChange: (index: number) => void;
  onRetry: (index: number) => void;
  selectedProject?: Project | null;
  showToast: ShowToast;
}

/** Aktionen unter einer Antwort (kopieren, Zitatansicht, Bewertung, wiederholen, Erkenntnis) und das Modell. */
export function ChatMessageActions({
  message: m,
  index: i,
  theme,
  isLoading,
  showOriginal,
  onToggleOriginal,
  onFeedback,
  onRetry,
  selectedProject,
  showToast,
  versionIndex,
  onVersionChange,
}: ChatMessageActionsProps) {
  const [askReason, setAskReason] = useState(false);
  const versionCount = (m.metadata?.versions?.length ?? 0) + 1;
  const { t, language } = useLanguage();
  const responseMs = m.metadata?.telemetry?.metrics?.response_time_ms ?? null;
  return (
    <>
    <div className="mt-3 pt-2 flex items-center justify-between gap-1.5">
      <div className="flex items-center gap-0.5 opacity-60 hover:opacity-100 transition-opacity">
        {versionCount > 1 && (
          <div className="flex items-center text-[0.625rem] font-semibold text-ds-zinc-500" aria-label={t('chatView.answerVersions')}>
            <Button variant="ghost" size="icon" className="h-6 w-6" disabled={versionIndex === 0}
              aria-label={t('chatView.previousVersion')} onClick={() => onVersionChange(versionIndex - 1)}>
              <ChevronLeft className="w-3.5 h-3.5" />
            </Button>
            <span>{versionIndex + 1}/{versionCount}</span>
            <Button variant="ghost" size="icon" className="h-6 w-6" disabled={versionIndex >= versionCount - 1}
              aria-label={t('chatView.nextVersion')} onClick={() => onVersionChange(versionIndex + 1)}>
              <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          id={`chat-action-copy-btn-${i}`}
          title={t('chatView.copyMessageTitle')}
          className={cn("h-7 w-7 rounded-full", theme === 'dark' ? "text-ds-zinc-500 hover:text-ds-zinc-300 hover:bg-ds-zinc-800" : "text-ds-zinc-500 hover:text-ds-zinc-800 hover:bg-ds-zinc-100")}
          onClick={async () => {
            const success = await copyToClipboard(m.content);
            showToast(success ? t('chatView.messageCopiedToast') : t('chatView.copyFailedToast'), success ? "success" : "error");
          }}
        >
          <Copy className="w-3.5 h-3.5" />
        </Button>
        {hasCompactableCitation(m.content) && (
          <Button
            variant="ghost"
            size="icon"
            aria-pressed={showOriginal}
            title={t(showOriginal ? 'chatView.showCompactCitations' : 'chatView.showOriginalAnswer')}
            aria-label={t(showOriginal ? 'chatView.showCompactCitations' : 'chatView.showOriginalAnswer')}
            className={cn("h-7 w-7 rounded-full", theme === 'dark' ? "text-ds-zinc-500 hover:text-ds-zinc-300 hover:bg-ds-zinc-800" : "text-ds-zinc-500 hover:text-ds-zinc-800 hover:bg-ds-zinc-100")}
            onClick={onToggleOriginal}
          >
            <FolderTree className="w-3.5 h-3.5" />
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          id={`chat-action-thumbsup-btn-${i}`}
          title={t('chatView.helpfulTitle')}
          disabled={!m.id}
          className={cn(
            "h-7 w-7 rounded-full",
            m.feedback === 'up'
              ? "text-ds-emerald-500"
              : (theme === 'dark' ? "text-ds-zinc-500 hover:text-ds-zinc-300 hover:bg-ds-zinc-800" : "text-ds-zinc-500 hover:text-ds-zinc-800 hover:bg-ds-zinc-100")
          )}
          onClick={() => m.id && onFeedback(m.id, 'up')}
        >
          <ThumbsUp className="w-3.5 h-3.5" fill={m.feedback === 'up' ? "currentColor" : "none"} />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          id={`chat-action-thumbsdown-btn-${i}`}
          title={t('chatView.notHelpfulTitle')}
          disabled={!m.id}
          className={cn(
            "h-7 w-7 rounded-full",
            m.feedback === 'down'
              ? "text-ds-red-500"
              : (theme === 'dark' ? "text-ds-zinc-500 hover:text-ds-zinc-300 hover:bg-ds-zinc-800" : "text-ds-zinc-500 hover:text-ds-zinc-800 hover:bg-ds-zinc-100")
          )}
          onClick={() => {
            if (!m.id) return;
            onFeedback(m.id, 'down');
            setAskReason(m.feedback !== 'down');
          }}
        >
          <ThumbsDown className="w-3.5 h-3.5" fill={m.feedback === 'down' ? "currentColor" : "none"} />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          id={`chat-action-retry-btn-${i}`}
          title={t('chatView.retryTitle')}
          disabled={!m.id || isLoading}
          className={cn("h-7 w-7 rounded-full", theme === 'dark' ? "text-ds-zinc-500 hover:text-ds-zinc-300 hover:bg-ds-zinc-800" : "text-ds-zinc-500 hover:text-ds-zinc-800 hover:bg-ds-zinc-100")}
          onClick={() => onRetry(i)}
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </Button>

        {m.metadata?.chat_mode === 'evidence' && (
          <InsightDraftAction
            projectId={selectedProject?.id}
            origin="chat"
            evidence={chatInsightEvidence(m.sources || [], m.id)}
            defaultTitle={m.content.split('\n')[0].slice(0, 240) || t('insightDraft.chatDefaultTitle')}
            theme={theme}
          />
        )}
      </div>

      {m.metadata && m.metadata.model && (
        <div className={cn(
          "flex items-center gap-1.5 opacity-60 hover:opacity-100 transition-opacity",
          theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-400"
        )}>
          <Cpu className="w-3 h-3" />
          <span className="text-[0.625rem] font-bold uppercase tracking-widest">{m.metadata.model}</span>
          {m.metadata.chat_mode && <span className="text-[0.625rem] font-semibold">· {t(`chatView.mode.${m.metadata.chat_mode}`)}</span>}
          {responseMs != null && (
            <span className="text-[0.625rem] font-semibold" title={t('chatView.responseTimeTitle')}>
              · {new Intl.NumberFormat(language, { maximumFractionDigits: 1 }).format(responseMs / 1000)} s
            </span>
          )}
        </div>
      )}
    </div>
    {askReason && m.id && (
      <FeedbackReasonPicker theme={theme} onClose={() => setAskReason(false)}
        onSubmit={(reason, comment) => { onFeedback(m.id as number, 'down', reason, comment); setAskReason(false); }} />
    )}
    </>
  );
}
