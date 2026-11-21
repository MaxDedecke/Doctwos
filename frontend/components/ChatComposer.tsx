"use client";
import type { ShowToast } from './Toast';
import type { LlmProfile } from '@/hooks/useAiSettings';
import type { ChatPinnedFocus } from '@/lib/chatFocus';
import type { KnowledgeSource, Project, SearchResult } from '@/types/domain';
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select";
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from "@/lib/utils";
import { AtSign, BookOpen, Check, Code, Cpu, Pencil, Plus, Send, Square, X } from 'lucide-react';
import { applyMention, useEntityMentions } from '@/hooks/useEntityMentions';
import { useState } from 'react';

export interface ChatComposerProps {
  theme: string;
  currentMessage: string;
  setCurrentMessage: (message: string) => void;
  handleSendChat: () => void;
  isLoading: boolean;
  /** Bricht die laufende Antwort ab (Knopf oder Esc). */
  onStop: () => void;
  /** Die letzte Frage wird gerade bearbeitet; Senden ersetzt sie samt Antwort. */
  editing: boolean;
  canEditLast: boolean;
  onEditLast: () => void;
  onCancelEdit: () => void;
  selectedProject: Project | null;
  selectedSource: KnowledgeSource | null;
  setSelectedSource: (source: KnowledgeSource | null) => void;
  pinnedCode: ChatPinnedFocus | null;
  setPinnedCode: (pin: ChatPinnedFocus | null) => void;
  filteredSources: KnowledgeSource[];
  handleSourceFocusChange: (source: KnowledgeSource | null) => void;
  sessionChatMode: 'normal' | 'evidence' | null;
  activeChatMode: 'normal' | 'evidence';
  activeProfileId: string;
  setActiveProfileId: (value: string) => void;
  llmProfiles: LlmProfile[];
  showToast: ShowToast;
}

/** Eingabeleiste des Chats: Fokus-Chips, Eingabefeld, Quellen- und Modellwahl, Senden bzw. Stoppen. */
export function ChatComposer({
  theme, currentMessage, setCurrentMessage, handleSendChat, isLoading, onStop, editing, canEditLast, onEditLast,
  onCancelEdit, selectedProject, selectedSource, setSelectedSource, pinnedCode, setPinnedCode, filteredSources,
  handleSourceFocusChange, sessionChatMode, activeChatMode, activeProfileId, setActiveProfileId, llmProfiles, showToast,
}: ChatComposerProps) {
  const { t } = useLanguage();
  const [caret, setCaret] = useState(0);
  const mentions = useEntityMentions(currentMessage, caret, selectedProject?.id);
  const chooseMention = (item: SearchResult) => {
    const next = applyMention(currentMessage, caret, item.node_label);
    if (!next) return;
    setCurrentMessage(next.text);
    setCaret(next.caret);
    requestAnimationFrame(() => {
      const field = document.getElementById('chat-textarea') as HTMLTextAreaElement | null;
      field?.setSelectionRange(next.caret, next.caret);
    });
  };
  // Bewusst kompakt: Im Viertelraster (4 Ansichten) ist die Höhe des Chats knapp, und Container-Queries sehen
  // nur die Breite.
  return (
    <div className={cn(
      "px-3 pb-2 pt-1 bg-transparent z-20 transition-colors",
      theme === 'dark' ? "border-ds-zinc-900/40" : "border-ds-zinc-200"
    )}>
      <div className="w-[92%] max-w-3xl mx-auto relative group">
        {mentions.open && (
          <ul role="listbox" aria-label={t('chatView.mentionsLabel')} className={cn("absolute bottom-full left-0 right-0 mb-1 max-h-56 overflow-y-auto rounded-lg border p-1 text-xs shadow-xl",
            theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200")}>
            {mentions.items.map((item, index) => (
              <li key={`${item.node_type}:${item.node_id}`} role="option" aria-selected={index === mentions.active}
                onMouseDown={(event) => { event.preventDefault(); chooseMention(item); }}
                className={cn("flex cursor-pointer items-center gap-2 rounded px-2 py-1", index === mentions.active && "bg-ds-indigo-500/10")}>
                <AtSign className="w-3 h-3 shrink-0 text-ds-indigo-500" />
                <span className="font-mono font-semibold">{item.node_label}</span>
                <span className="truncate text-ds-zinc-500">{[item.node_meta.type, item.node_meta.file_path].filter(Boolean).join(' · ')}</span>
              </li>
            ))}
          </ul>
        )}

        <div className={cn(
          "border rounded-lg shadow-2xl transition-all shadow-ds-black/40 backdrop-blur-xl w-full max-w-full overflow-hidden",
          theme === 'dark'
            ? "bg-ds-zinc-900/60 border-ds-zinc-800/80"
            : "bg-ds-white border-ds-zinc-200"
        )}>
          {/* Active project contextual focus helper and Pinned Code location helper */}
          {(selectedSource || pinnedCode || editing) && (
            <div className={cn(
              "flex flex-wrap items-center gap-1.5 px-3 pt-1.5 pb-1.5 border-b transition-colors",
              theme === 'dark' ? "border-ds-zinc-800/40" : "border-ds-zinc-200/60"
            )}>
              {editing && (
                <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-sm bg-ds-amber-500/10 border border-ds-amber-500/20 text-ds-amber-600 text-[0.625rem] font-semibold">
                  <Pencil className="w-3 h-3 shrink-0" />
                  <span>{t('chatView.editingQuestion')}</span>
                  <button type="button" onClick={onCancelEdit} className="ml-1 p-0.5 rounded" title={t('chatView.cancelEdit')} aria-label={t('chatView.cancelEdit')}>
                    <X className="w-2.5 h-2.5" />
                  </button>
                </div>
              )}
              {selectedSource && (
                <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-sm bg-ds-blue-500/10 border border-ds-blue-500/20 text-ds-blue-500 text-[0.625rem] font-semibold tracking-wide shadow-sm max-w-full">
                  <BookOpen className="w-3 h-3 text-ds-blue-400 shrink-0" />
                  <span className="truncate max-w-[140px] @sm/chat:max-w-[220px]">{t('chatView.sourceLabel', { name: selectedSource.name })}</span>
                  <button
                    type="button"
                    onClick={() => setSelectedSource(null)}
                    id="clear-chat-source-focus-btn"
                    className="hover:text-ds-blue-850 transition-colors ml-1 p-0.5 rounded"
                    title={t('chatView.clearSourceFocusTitle')}
                  >
                    <X className="w-2.5 h-2.5" />
                  </button>
                </div>
              )}

              {pinnedCode && (
                <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-sm bg-ds-emerald-500/10 border border-ds-emerald-500/20 text-ds-emerald-500 text-[0.625rem] font-semibold tracking-wide shadow-sm max-w-full">
                  <Code className="w-3 h-3 text-ds-emerald-400 shrink-0" />
                  <span className="truncate max-w-[140px] @sm/chat:max-w-[220px]" title={pinnedCode.context || `${pinnedCode.filepath}:${pinnedCode.line}`}>
                    {t('chatView.pinLabel', { path: pinnedCode.breadcrumb || pinnedCode.label || `${pinnedCode.filepath.split('/').pop()}:${pinnedCode.line}` })}
                  </span>
                  <button
                    type="button"
                    onClick={() => setPinnedCode(null)}
                    id="clear-chat-pinned-code-btn"
                    className="hover:text-ds-emerald-850 transition-colors ml-1 p-0.5 rounded"
                    title={t('chatView.clearPinTitle')}
                  >
                    <X className="w-2.5 h-2.5" />
                  </button>
                </div>
              )}
            </div>
          )}

          <textarea
            onSelect={(e) => setCaret(e.currentTarget.selectionStart ?? 0)}
            rows={1}
            id="chat-textarea"
            className={cn(
              "min-h-[36px] max-h-40 w-full bg-transparent border-0 focus:ring-0 focus:outline-none focus-visible:ring-0 focus-visible:outline-none px-3 pt-2 pb-1.5 resize-none text-[0.8125rem] outline-none overflow-y-auto",
              theme === 'dark' ? "text-ds-zinc-100 placeholder:text-ds-zinc-650" : "text-ds-zinc-900 placeholder:text-ds-zinc-400"
            )}
            placeholder={t('chatView.inputPlaceholder')}
            value={currentMessage}
            onChange={(e) => {
              setCurrentMessage(e.target.value);
              setCaret(e.target.selectionStart ?? e.target.value.length);
              // Wächst bis max-h-40 (160 px, ~8 Zeilen) mit und scrollt dann innen; im Viertelraster ist die Höhe knapp.
              e.target.style.height = 'auto';
              e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
            }}
            onKeyDown={(e) => {
              if (mentions.open && ['ArrowDown', 'ArrowUp', 'Enter', 'Tab', 'Escape'].includes(e.key)) {
                e.preventDefault();
                if (e.key === 'ArrowDown') mentions.move(1);
                else if (e.key === 'ArrowUp') mentions.move(-1);
                else if (e.key === 'Escape') mentions.dismiss();
                else chooseMention(mentions.items[mentions.active]);
                return;
              }
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (!isLoading) handleSendChat();
              } else if (e.key === 'Escape' && isLoading) {
                e.preventDefault();
                onStop();
              } else if (e.key === 'Escape' && editing) {
                e.preventDefault();
                onCancelEdit();
              } else if (e.key === 'ArrowUp' && !currentMessage && canEditLast) {
                e.preventDefault();
                onEditLast();
              }
            }}
          />
          <div className={cn("flex items-center justify-between px-3 pb-2 pt-1 border-t flex-wrap gap-1.5", theme === 'dark' ? "border-ds-zinc-800/40" : "border-ds-zinc-200/60")}>
             <div className="flex items-center gap-1.5 flex-wrap flex-1 min-w-0">
                {/* Knowledge-source focus lives behind this "+" by default. Project
                    focus is chosen centrally in the page header now (see GlobalSearch),
                    not duplicated here. */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      id="chat-focus-more-btn"
                      title={t('chatView.moreOptionsTitle')}
                      className={cn(
                        "relative h-7 w-7 shrink-0 flex items-center justify-center rounded-lg border transition-all",
                        theme === 'dark' ? "bg-ds-zinc-900/80 border-ds-zinc-800 text-ds-zinc-300 hover:bg-ds-zinc-800/40" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-700 hover:bg-ds-zinc-50"
                      )}
                    >
                      <Plus className="w-3.5 h-3.5" />
                      {selectedSource && (
                        <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-ds-indigo-500 border border-ds-white dark:border-ds-zinc-900" />
                      )}
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="start"
                    className={cn("w-64", theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-800")}
                  >
                    <DropdownMenuLabel className="text-[0.5625rem] font-bold uppercase tracking-wider text-ds-zinc-500">
                      {selectedProject ? t('chatView.sourcesForProject', { name: selectedProject.name }) : t('chatView.globalSources')}
                    </DropdownMenuLabel>
                    <DropdownMenuItem className="text-xs gap-2" onClick={() => handleSourceFocusChange(null)}>
                      <Check className={cn("w-3.5 h-3.5 shrink-0", !selectedSource ? "opacity-100" : "opacity-0")} />
                      {t('chatView.noKnowledgeSource')}
                    </DropdownMenuItem>
                    {filteredSources && filteredSources.length > 0 ? (
                      filteredSources.map((src) => (
                        <DropdownMenuItem
                          key={src.id}
                          className="text-xs gap-2"
                          onClick={() => handleSourceFocusChange(src)}
                        >
                          <Check className={cn("w-3.5 h-3.5 shrink-0", selectedSource?.id === src.id ? "opacity-100" : "opacity-0")} />
                          <span className="truncate">{src.name} ({src.type})</span>
                        </DropdownMenuItem>
                      ))
                    ) : (
                      <div className="px-2 py-1.5 text-xs text-ds-zinc-500 italic">
                        {t('chatView.noKnowledgeSource')}
                      </div>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>

                {sessionChatMode && (
                  <span
                    data-testid="chat-mode-badge"
                    title={`${t('chatView.modeLabel')}: ${t(`chatView.mode.${sessionChatMode}Description`)}`}
                    className={cn(
                      "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-lg border px-2 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.16em] shadow-sm",
                      theme === 'dark' ? "bg-ds-zinc-900/80 border-ds-zinc-800 text-ds-zinc-300" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-700"
                    )}
                  >
                    <span aria-hidden="true" className={cn("h-1.5 w-1.5 rounded-full", sessionChatMode === 'evidence' ? "bg-ds-indigo-500" : "bg-ds-zinc-500")} />
                    <span className="sr-only">{t('chatView.modeLabel')}: </span>
                    {t(`chatView.mode.${sessionChatMode}`)}
                  </span>
                )}

                <Select
                  value={activeProfileId}
                  onValueChange={(val) => {
                    setActiveProfileId(val);
                    const selectedProf = llmProfiles.find(p => p.id === val);
                    if (selectedProf) {
                      showToast(t('chatView.modelSwitchedToast', { name: selectedProf.name }), "success");
                    }
                  }}
                >
                  <SelectTrigger aria-label={t('chatView.selectModel')} className={cn(
                    "h-7 w-7 @sm/chat:w-auto @sm/chat:max-w-[160px] @sm/chat:min-w-[110px] text-xs border focus:ring-0 shrink-0 rounded-lg font-medium shadow-sm transition-all flex items-center justify-center @sm/chat:justify-between gap-1 px-0 @sm/chat:px-2.5 [&>svg]:hidden @sm/chat:[&>svg]:block",
                    theme === 'dark' ? "bg-ds-zinc-900/80 border-ds-zinc-800 text-ds-zinc-300 hover:bg-ds-zinc-800/40" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-700 hover:bg-ds-zinc-50"
                  )}>
                    <div className="flex items-center gap-1.5 truncate">
                      <Cpu className="w-3.5 h-3.5 text-ds-indigo-500 shrink-0" />
                      <span className="hidden @sm/chat:inline truncate">
                        {llmProfiles.find(p => p.id === activeProfileId)?.name || t('chatView.selectModel')}
                      </span>
                    </div>
                  </SelectTrigger>
                  <SelectContent className={theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-800"}>
                    {llmProfiles.map((prof) => (
                      <SelectItem key={prof.id} value={prof.id} className="text-xs">
                        {prof.name} ({prof.model})
                        {prof.capabilities?.tools === false && <span className="ml-1 text-ds-amber-600">· {t('chatView.modelWithoutTools')}</span>}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

             </div>
             {isLoading ? (
               <Button size="icon" id="stop-chat-message-btn" aria-label={t('chatView.stopAnswer')} title={t('chatView.stopAnswerTitle')}
                 onClick={onStop} className={cn("h-8 w-8 rounded-lg", theme === 'dark' ? "bg-ds-zinc-100 text-ds-zinc-900 hover:bg-ds-zinc-300" : "bg-ds-zinc-900 text-ds-white hover:bg-ds-zinc-700")}>
                 <Square className="w-3 h-3" fill="currentColor" />
               </Button>
             ) : (
               <Button
                           size="icon"
                           id="send-chat-message-btn"
                           aria-label={t('chatView.sendMessageLabel')}
                           disabled={!currentMessage.trim()}
                           onClick={() => handleSendChat()}
                           className={cn(
                               "h-8 w-8 rounded-lg transition-all font-semibold",
                               currentMessage.trim()
                                 ? (theme === 'dark'
                                     ? "bg-ds-zinc-800 text-ds-zinc-100 hover:bg-ds-zinc-700"
                                     : "bg-transparent text-ds-zinc-900 hover:bg-ds-zinc-900/10")
                                 : (theme === 'dark'
                                     ? "bg-ds-zinc-800 text-ds-zinc-650 opacity-50 cursor-not-allowed"
                                     : "bg-ds-zinc-100 text-ds-zinc-400 opacity-50 cursor-not-allowed")
                           )}
                        >
                           <Send className="w-3.5 h-3.5" />
                        </Button>
             )}
          </div>
        </div>
        {/* AI Warning Disclaimer */}
        <div className="mt-1 text-[0.625rem] leading-snug text-ds-zinc-500 text-center px-3">
          {t(activeChatMode === 'normal' ? 'chatView.mode.normalDescription' : 'chatView.mode.evidenceDescription')}
          <span className="hidden @md/chat:inline"> · {t('chatView.inputHint')}</span>
        </div>
      </div>
    </div>
  );
}
