"use client";

import React from 'react';
import {
  MessageSquare,
  Code,
  Send,
  Database,
  Sparkles,
  Folder,
  X,
  Loader2,
  Cpu,
  GitBranch,
  Globe2,
  Share2,
  History,
  BookOpen,
  Copy,
  ThumbsUp,
  ThumbsDown,
  RotateCcw,
  Plus,
  Check,
  ArrowRight
} from 'lucide-react';
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MarkdownContent } from "@/components/MarkdownContent";
import { AgentSteps } from "./AgentSteps";
import { cn, copyToClipboard } from "@/lib/utils";
import { DoctusIcon } from "@/components/Logo";
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { api } from '@/app/services/api';

interface ChatViewProps {
  theme: string;
  isSidebarOpen: boolean;
  selectedProject: any;
  onProjectSelect: (project: any | null) => void | Promise<void>;
  pinnedCode: any;
  setPinnedCode: (code: any) => void;
  chatMessages: any[];
  currentMessage: string;
  setCurrentMessage: (msg: string) => void;
  isLoading: boolean;
  activeSessionId: number | null;
  handleSendChat: (overrideMsg?: string, extraMetadata?: Record<string, any>) => void;
  handleRetryMessage: (index: number) => void;
  handleFeedback: (messageId: number, feedback: 'up' | 'down') => void;
  addAssistantHint: (text: string) => void;
  handleFileSelect: (path: string, line?: number, sourceId?: string) => void;
  activeProfileId: string;
  setActiveProfileId: (val: string) => void;
  llmProfiles: any[];
  showToast: (msg: string, type: "success" | "error") => void;
  selectedFile: any;
  selectedDoc: any;
  splitClasses: { chat: string; editor: string };
  chatEndRef: React.RefObject<HTMLDivElement | null>;
  selectedSource: any;
  setSelectedSource: (source: any) => void;
  connectedSources: any[];
}

export function ChatView({
  theme,
  isSidebarOpen,
  selectedProject,
  onProjectSelect,
  pinnedCode,
  setPinnedCode,
  chatMessages,
  currentMessage,
  setCurrentMessage,
  isLoading,
  activeSessionId,
  handleSendChat,
  handleRetryMessage,
  handleFeedback,
  addAssistantHint,
  handleFileSelect,
  activeProfileId,
  setActiveProfileId,
  llmProfiles,
  showToast,
  selectedFile,
  selectedDoc,
  splitClasses,
  chatEndRef,
  selectedSource,
  setSelectedSource,
  connectedSources
}: ChatViewProps) {
  const { t } = useLanguage();

  const [detectedLph, setDetectedLph] = React.useState<number | null>(null);
  const [recommendedChecklists, setRecommendedChecklists] = React.useState<string[]>([]);
  const [typingText, setTypingText] = React.useState("");
  const [isTyping, setIsTyping] = React.useState(false);

  React.useEffect(() => {
    if (chatMessages.length > 0) return;

    let typingInterval: NodeJS.Timeout | null = null;
    let minuteInterval: NodeJS.Timeout | null = null;

    const startTyping = (text: string) => {
      if (typingInterval) clearInterval(typingInterval);
      let index = 0;
      setTypingText("");
      setIsTyping(true);
      typingInterval = setInterval(() => {
        if (index < text.length) {
          // text.charAt(index) must be captured now, not inside the updater: React can
          // defer invoking the updater until after later ticks have already bumped
          // `index`, which drops/duplicates characters (index no longer matches when
          // the closure reads it).
          const nextChar = text.charAt(index);
          setTypingText((prev) => prev + nextChar);
          index++;
        } else {
          setIsTyping(false);
          if (typingInterval) clearInterval(typingInterval);
        }
      }, 70); // 70ms per character
    };

    const fetchNextStatement = async () => {
      try {
        const res = await api.getTypingStatement();
        if (res.data?.statement) {
          startTyping(res.data.statement);
        }
      } catch (err) {
        console.error("Failed to fetch typing statement", err);
        const fallbacks = [
          t('chatView.typingFallbacks.makeCobolKnowledgeVisible'),
          t('chatView.typingFallbacks.navigateMainframeCode'),
          t('chatView.typingFallbacks.unlockLegacySystems'),
          t('chatView.typingFallbacks.programsCopybooksRelations')
        ];
        const randomPhrase = fallbacks[Math.floor(Math.random() * fallbacks.length)];
        startTyping(randomPhrase);
      }
    };

    fetchNextStatement();

    minuteInterval = setInterval(() => {
      fetchNextStatement();
    }, 60000);

    return () => {
      if (typingInterval) clearInterval(typingInterval);
      if (minuteInterval) clearInterval(minuteInterval);
    };
  }, [chatMessages.length, t]);
  const [isDetectingLph, setIsDetectingLph] = React.useState(false);

  React.useEffect(() => {
    const API_URL = (typeof window !== "undefined" && (window as any).__DOCTUS_API_URL__) || "http://localhost:8000";
    (async () => {
      if (!selectedFile) {
        setDetectedLph(null);
        setRecommendedChecklists([]);
        return;
      }
      setIsDetectingLph(true);
      try {
        const res = await fetch(`${API_URL}/aec/hoai/detect-lph`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ file_path: selectedFile, project_id: selectedProject?.id ?? null })
        });
        if (res.ok) {
          const data = await res.json();
          setDetectedLph(data.lph);
          setRecommendedChecklists(data.recommended_checklists || []);
        }
      } catch (err) {
        console.error("LPH detection failed:", err);
      } finally {
        setIsDetectingLph(false);
      }
    })();
  }, [selectedFile, selectedProject?.id]);

  const filteredSources = React.useMemo(() => {
    if (!connectedSources) return [];
    if (!selectedProject) {
      return connectedSources;
    }
    return connectedSources.filter(src => {
      const srcProjectId = src.project_id !== undefined ? src.project_id : src.repo_id;
      const isGlobal = srcProjectId === null || srcProjectId === 'all' || !srcProjectId;
      return isGlobal || srcProjectId === selectedProject.id || srcProjectId === selectedProject.id.toString();
    });
  }, [connectedSources, selectedProject]);

  const handleSourceFocusChange = (source: any | null) => {
    setSelectedSource(source);
  };

  return (
    <div className={cn(
      "@container/chat h-full flex flex-col transition-all duration-300 ease-in-out relative",
      (selectedFile || selectedDoc) ? splitClasses.chat : "w-full"
    )}>

      {/* Upper Spacer to offset Sidebar Menu button */}
      <div className={cn(
        "h-16 flex items-center justify-end px-4 @sm/chat:px-6 backdrop-blur-sm bg-opacity-20 transition-colors duration-250",
        theme === 'dark' ? "bg-ds-zinc-950/20" : "bg-ds-zinc-100/20"
      )}>
        <div className="flex flex-col items-end gap-1.5 py-2">
          <div className={cn(
            "flex items-center gap-2 border px-2 @sm/chat:px-3 py-1 rounded-sm text-xs font-semibold tracking-wide shadow-sm",
            selectedProject
              ? "bg-ds-indigo-500/10 border-ds-indigo-500/20 text-ds-indigo-650"
              : theme === 'dark'
                ? "bg-ds-zinc-800/50 border-ds-zinc-700/60 text-ds-zinc-400"
                : "bg-ds-zinc-100/70 border-ds-zinc-200 text-ds-zinc-500"
          )}>
            {selectedProject ? (
              <>
                <Database className="w-3.5 h-3.5 text-ds-indigo-500 shrink-0" />
                <span className="hidden @xs/chat:inline">{t('chatView.projectLabel', { name: selectedProject.name })}</span>
                <button
                  type="button"
                  onClick={() => onProjectSelect(null)}
                  id="clear-chat-project-focus-btn"
                  className="hover:text-ds-indigo-850 transition-colors ml-0.5 p-0.5 rounded"
                  title={t('chatView.clearContextTitle')}
                  aria-label={t('chatView.clearContextTitle')}
                >
                  <X className="w-3 h-3" />
                </button>
              </>
            ) : (
              <>
                <Globe2 className="w-3.5 h-3.5 shrink-0" />
                <span>{t('chatView.generalContextLabel')}</span>
              </>
            )}
          </div>
            {isDetectingLph ? (
              <div className="flex items-center gap-1.5 text-[10px] text-ds-zinc-500">
                <Loader2 className="w-3 h-3 animate-spin" /> HOAI Copilot analysiert...
              </div>
            ) : detectedLph ? (
              <div className="flex items-center gap-2 mt-1">
                <span className="text-[10px] font-bold uppercase tracking-wider bg-ds-emerald-100 text-ds-emerald-700 px-2 py-0.5 rounded-md dark:bg-ds-emerald-900/50 dark:text-ds-emerald-400">
                  LPH {detectedLph} erkannt
                </span>
                {recommendedChecklists.map((chk, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setCurrentMessage(`Ich benötige die Checkliste: ${chk}`);
                      const textarea = document.getElementById("chat-textarea") as HTMLTextAreaElement;
                      if (textarea) textarea.focus();
                    }}
                    className={cn(
                      "text-[9px] font-mono border rounded px-1.5 py-0.5 hover:bg-ds-zinc-200 transition-colors shadow-sm",
                      theme === 'dark' ? "border-ds-zinc-700 text-ds-zinc-300 hover:bg-ds-zinc-800" : "border-ds-zinc-300 text-ds-zinc-600"
                    )}
                  >
                    <BookOpen className="w-2.5 h-2.5 inline mr-1" />
                    {chk}
                  </button>
                ))}
              </div>
            ) : null}
        </div>
      </div>

      {/* Chat message stream container */}
      <ScrollArea className="flex-1 w-full min-w-0">
        <div className="w-full px-4 @sm/chat:px-6 py-6 @sm/chat:py-8 flex flex-col min-h-full justify-between max-w-4xl mx-auto">

          {/* Zero State / Welcomer */}
          {chatMessages.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-start text-center space-y-8 pt-8 pb-16 relative">

              {/* Glowing circular element behind greeting */}
              <div className={cn(
                "absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] rounded-full blur-[100px] pointer-events-none z-0",
                theme === 'dark' ? "bg-ds-indigo-600/5" : "bg-ds-indigo-500/5"
              )} />

              <div className="space-y-2 relative z-10 max-w-xl">
                <h1 className={cn("text-3xl @md/chat:text-4xl font-heading font-extrabold tracking-tight leading-tight transition-colors duration-250 text-center min-h-[40px]", theme === 'dark' ? "text-ds-white" : "text-ds-zinc-900")}>
                  <span className="inline-flex items-center justify-center gap-2.5 flex-wrap">
                    <span>{typingText}</span>
                    {!isTyping && typingText && (
                      <button
                        type="button"
                        onClick={() => handleSendChat(typingText)}
                        className={cn(
                          "group inline-flex items-center justify-center p-1.5 rounded-lg border transition-all duration-200 cursor-pointer shadow-sm hover:scale-105 active:scale-95 shrink-0 align-middle",
                          theme === 'dark'
                            ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-indigo-400 hover:text-ds-indigo-350 hover:bg-ds-zinc-850 hover:border-ds-zinc-700"
                            : "bg-ds-white border-ds-zinc-200 text-ds-indigo-650 hover:text-ds-indigo-700 hover:bg-ds-zinc-50 hover:border-ds-zinc-300"
                        )}
                        title={t('chatView.askDirectlyTitle')}
                      >
                        <ArrowRight className="w-4 h-4 transition-transform duration-200 group-hover:translate-x-0.5" />
                      </button>
                    )}
                  </span>
                </h1>
              </div>

              {/* Pre-canned Suggestions grids */}
              <div className="grid grid-cols-1 @lg/chat:grid-cols-2 gap-4 w-full max-w-2xl relative z-10">
                {[
                  { id: 'explainProgram', label: t('chatView.suggestions.explainProgram.label'), icon: <Code className="w-4.5 h-4.5 text-ds-blue-500" />, desc: t('chatView.suggestions.explainProgram.desc'), clarify: t('chatView.suggestions.explainProgram.clarify'), template: t('chatView.suggestions.explainProgram.template') },
                  { id: 'traceCall', label: t('chatView.suggestions.traceCall.label'), icon: <Database className="w-4.5 h-4.5 text-ds-indigo-500" />, desc: t('chatView.suggestions.traceCall.desc'), clarify: t('chatView.suggestions.traceCall.clarify'), template: t('chatView.suggestions.traceCall.template') },
                  { id: 'summarizeDocs', label: t('chatView.suggestions.summarizeDocs.label'), icon: <History className="w-4.5 h-4.5 text-ds-emerald-500" />, desc: t('chatView.suggestions.summarizeDocs.desc') },
                  { id: 'findField', label: t('chatView.suggestions.findField.label'), icon: <Sparkles className="w-4.5 h-4.5 text-ds-amber-500" />, desc: t('chatView.suggestions.findField.desc'), clarify: t('chatView.suggestions.findField.clarify'), template: t('chatView.suggestions.findField.template') }
                ].map((hint, idx) => {
                  const isOnboarding = hint.id === 'summarizeDocs';
                  const isDisabled = isOnboarding && !selectedProject;
                  return (
                  <button
                    type="button"
                    key={idx}
                    id={`chat-hint-button-${idx}`}
                    disabled={isDisabled}
                    title={isDisabled ? t('chatView.suggestions.summarizeDocs.noProjectTooltip') : undefined}
                    onClick={() => {
                      if (isOnboarding) {
                        if (!selectedProject) {
                          showToast(t('chatView.suggestions.summarizeDocs.noProjectToast'), "error");
                          return;
                        }
                        handleSendChat(t('chatView.suggestions.summarizeDocs.triggerMessage'), { intent: "onboarding" });
                        return;
                      }
                      // These cards name a topic but leave out the one detail
                      // the LLM would need (which program/objects/field) — so
                      // instead of pasting the bare label, we show the
                      // clarifying question the LLM would ask and prefill the
                      // textarea with a self-contained sentence stub for it.
                      if ('clarify' in hint && hint.clarify) {
                        addAssistantHint(hint.clarify);
                        setCurrentMessage(hint.template || "");
                      } else {
                        setCurrentMessage(hint.label);
                      }
                      // Deferred a tick: the textarea's value is controlled by
                      // currentMessage, which hasn't re-rendered into the DOM
                      // yet at this point in the click handler.
                      requestAnimationFrame(() => {
                        const textarea = document.getElementById("chat-textarea") as HTMLTextAreaElement;
                        if (textarea) {
                          textarea.focus();
                          const len = textarea.value.length;
                          textarea.setSelectionRange(len, len);
                        }
                      });
                    }}
                    className={cn(
                      "group p-4 border rounded-lg transition-all text-left flex items-start gap-4 shadow-sm",
                      isDisabled && "opacity-50 cursor-not-allowed",
                      theme === 'dark'
                        ? "bg-ds-zinc-900/40 border-ds-zinc-800/80 hover:bg-ds-zinc-800/50 hover:border-ds-zinc-700/80 text-ds-zinc-200 hover:shadow-[0_0_20px_rgba(99,102,241,0.08)]"
                        : "bg-ds-white border-ds-zinc-200 hover:bg-ds-zinc-50 hover:border-ds-zinc-300 text-ds-zinc-800 hover:shadow-md hover:-translate-y-0.5"
                    )}
                  >
                    <div className={cn(
                      "p-2.5 rounded-lg border transition-colors shadow-inner",
                      theme === 'dark' ? "bg-ds-zinc-950 border-ds-zinc-800/80 group-hover:bg-ds-zinc-900" : "bg-ds-zinc-50 border-ds-zinc-200 group-hover:bg-ds-zinc-100"
                    )}>
                      {hint.icon}
                    </div>
                    <div className="space-y-0.5">
                      <span className="block text-xs font-bold">{hint.label}</span>
                      <span className="block text-[10px] text-ds-zinc-500 font-medium">{hint.desc}</span>
                    </div>
                  </button>
                  );
                })}
              </div>
            </div>
          ) : (
            // Message Stream
            <div className="space-y-6 pb-6">
              {chatMessages.map((m, i) => {
                const isUser = m.role === 'user';
                return (
                  <div
                    key={i}
                    className={cn(
                      "flex gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300",
                      isUser ? "justify-end" : "justify-start"
                    )}
                  >
                    {/* Avatar for Assistant */}
                    {!isUser && (
                      <div className="w-7 h-7 @sm/chat:w-8 @sm/chat:h-8 rounded-lg flex items-center justify-center shrink-0 border border-ds-blue-500/20 bg-ds-blue-500/10 shadow-lg shadow-ds-blue-500/10">
                        <DoctusIcon className="w-4 h-4" />
                      </div>
                    )}

                    {/* Message Bubble */}
                    <div className={cn(
                      "max-w-[calc(100%-3rem)] @md/chat:max-w-[85%] min-w-0 text-sm leading-relaxed",
                      isUser
                        ? (theme === 'dark'
                            ? "bg-ds-zinc-900/95 border border-ds-zinc-800/80 text-ds-zinc-100 rounded-lg px-5 py-3 shadow-lg"
                            : "bg-ds-white border border-ds-zinc-200 text-ds-zinc-900 rounded-lg px-5 py-3 shadow-md shadow-ds-zinc-100")
                        : (theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-800")
                    )}>
                      {isUser ? (
                        <>
                          {m.metadata && (m.metadata.project || m.metadata.pinned || m.metadata.refs?.length) && (
                            <div className="flex flex-wrap gap-2 mb-2 pb-2 border-b border-ds-zinc-200/50 dark:border-ds-zinc-800/50">
                              {m.metadata.project && (
                                <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-ds-indigo-500/10 border border-ds-indigo-500/20 text-[10px] text-ds-indigo-400 font-bold uppercase tracking-tight">
                                  <Database className="w-3 h-3" />
                                  {m.metadata.project.name}
                                </div>
                              )}
                              {(m.metadata.refs?.length ? m.metadata.refs : (m.metadata.pinned ? [{
                                file: m.metadata.pinned.filepath,
                                line: m.metadata.pinned.line,
                                source_id: m.metadata.pinned.source_id
                              }] : [])).map((ref: any, refIndex: number) => (
                                <button
                                  type="button"
                                  onClick={() => handleFileSelect(
                                    ref.file,
                                    ref.line,
                                    ref.source_id ? String(ref.source_id) : undefined
                                  )}
                                  key={`${ref.file}:${ref.line}:${refIndex}`}
                                  className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-ds-emerald-500/10 border border-ds-emerald-500/20 text-[10px] text-ds-emerald-400 hover:bg-ds-emerald-500/20 hover:border-ds-emerald-500/40 font-bold uppercase tracking-tight transition-colors cursor-pointer"
                                  title={t('chatView.openPinnedLineTitle', { path: ref.file, line: ref.line })}
                                >
                                  <Code className="w-3 h-3" />
                                  {`${ref.file.split('/').pop()}:${ref.line}`}
                                </button>
                              ))}
                            </div>
                          )}
                          <p className="whitespace-pre-wrap font-medium">{m.content}</p>
                        </>
                      ) : (
                        <>
                          {m.metadata && m.metadata.agent_steps && m.metadata.agent_steps.length > 0 && (
                            <AgentSteps steps={m.metadata.agent_steps} theme={theme} isLive={isLoading && i === chatMessages.length - 1} />
                          )}

                          {m.content ? (
                            <MarkdownContent content={m.content} onFileClick={handleFileSelect} theme={theme} knownSources={m.sources} />
                          ) : (
                            isLoading && i === chatMessages.length - 1 && (!m.metadata?.agent_steps || m.metadata.agent_steps.length === 0) && (
                              <div className="flex items-center gap-2.5 text-ds-zinc-500/80 py-1.5 animate-pulse">
                                <Loader2 className="w-4 h-4 animate-spin text-ds-indigo-500 shrink-0" />
                                <span className="text-xs font-medium tracking-wide">{t('chatView.generatingResponse')}</span>
                              </div>
                            )
                          )}

                          {isLoading && i === chatMessages.length - 1 && (m.content || (m.metadata?.agent_steps && m.metadata.agent_steps.length > 0)) && (
                            <div className="flex items-center gap-2 text-ds-zinc-500/70 mt-3 py-1 font-medium select-none animate-pulse">
                              <Loader2 className="w-3.5 h-3.5 animate-spin text-ds-indigo-500 shrink-0" />
                              <span className="text-[11px] italic">{t('chatView.agentWorking')}</span>
                            </div>
                          )}

                          {/* Sources display if returned from query context */}
                          {m.sources && m.sources.length > 0 && (!isLoading || i !== chatMessages.length - 1) && (
                            <div className={cn(
                              "mt-4 pt-3 border-t flex flex-wrap gap-2 items-center transition-colors",
                              theme === 'dark' ? "border-ds-zinc-800/50" : "border-ds-zinc-200"
                            )}>
                              <span className="text-[10px] text-ds-zinc-500 font-bold uppercase tracking-wider">{t('chatView.referencedSources')}</span>
                              {m.sources.map((src, sIdx) => {
                                const filename = src.file.split('/').pop();
                                return (
                                  <button
                                    type="button"
                                    key={sIdx}
                                    id={`chat-source-link-${sIdx}`}
                                    onClick={() => handleFileSelect(src.file, src.lines && src.lines[0], src.source_id)}
                                    className={cn(
                                      "flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs transition-all shadow-inner font-medium cursor-pointer whitespace-nowrap max-w-full",
                                      theme === 'dark'
                                        ? "bg-ds-zinc-900/80 border-ds-zinc-800 hover:border-ds-zinc-700 text-ds-zinc-400 hover:text-ds-zinc-200"
                                        : "bg-ds-zinc-100/50 border-ds-zinc-200 hover:border-ds-zinc-300 text-ds-zinc-600 hover:text-ds-zinc-900"
                                    )}
                                    title={t('chatView.sourceFileTitle', { file: src.file, lines: src.lines.join('-') })}
                                  >
                                    <Folder className="w-3 h-3 text-ds-indigo-400 shrink-0" />
                                    <span className="font-mono text-[11px] font-semibold truncate min-w-0">{filename}</span>
                                    <span className="text-[9px] text-ds-zinc-500 font-mono shrink-0">L{src.lines.join('-')}</span>
                                  </button>
                                );
                              })}
                            </div>
                          )}

                          {/* Action row: copy / feedback / retry, plus model badge */}
                          {m.content && (!isLoading || i !== chatMessages.length - 1) && (
                            <div className="mt-3 pt-2 flex items-center justify-between gap-1.5">
                              <div className="flex items-center gap-0.5 opacity-60 hover:opacity-100 transition-opacity">
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
                                  onClick={() => handleFeedback(m.id, 'up')}
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
                                  onClick={() => handleFeedback(m.id, 'down')}
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
                                  onClick={() => handleRetryMessage(i)}
                                >
                                  <RotateCcw className="w-3.5 h-3.5" />
                                </Button>
                              </div>

                              {m.metadata && m.metadata.model && (
                                <div className={cn(
                                  "flex items-center gap-1.5 opacity-60 hover:opacity-100 transition-opacity",
                                  theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-400"
                                )}>
                                  <Cpu className="w-3 h-3" />
                                  <span className="text-[10px] font-bold uppercase tracking-widest">{m.metadata.model}</span>
                                </div>
                              )}
                            </div>
                          )}
                        </>
                      )}
                    </div>

                    {/* User Avatar */}
                    {isUser && (
                      <div className={cn(
                        "w-7 h-7 @sm/chat:w-8 @sm/chat:h-8 rounded-lg flex items-center justify-center shrink-0 border text-[10px] font-bold uppercase shadow-md transition-colors",
                        theme === 'dark' ? "border-ds-zinc-800 bg-ds-zinc-900 text-ds-zinc-400" : "border-ds-zinc-200 bg-ds-white text-ds-zinc-600"
                      )}>
                        ME
                      </div>
                    )}
                  </div>
                );
              })}


              <div ref={chatEndRef} />
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Float Input Action Bar -- kept deliberately compact: in a quarter-view
          (4 panels open at once) the chat pane's *height* is the scarce resource,
          not just its width, and container queries can't react to that, so this
          chrome stays small unconditionally rather than only at narrow widths. */}
      <div className={cn(
        "px-3 pb-2 pt-1 bg-opacity-20 backdrop-blur-sm z-20 transition-colors",
        theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-900/40" : "bg-ds-zinc-100/20 border-ds-zinc-200"
      )}>
        <div className="w-full max-w-4xl mx-auto relative group">

          <div className={cn(
            "border rounded-lg shadow-2xl transition-all shadow-ds-black/40 backdrop-blur-xl w-full max-w-full overflow-hidden",
            theme === 'dark'
              ? "bg-ds-zinc-900/60 border-ds-zinc-800/80"
              : "bg-ds-white border-ds-zinc-200"
          )}>
            {/* Active project contextual focus helper and Pinned Code location helper */}
            {(selectedProject || selectedSource || pinnedCode) && (
              <div className={cn(
                "flex flex-wrap items-center gap-1.5 px-3 pt-1.5 pb-1.5 border-b transition-colors",
                theme === 'dark' ? "border-ds-zinc-800/40" : "border-ds-zinc-200/60"
              )}>
                {selectedProject && (
                  <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-sm bg-ds-indigo-500/10 border border-ds-indigo-500/20 text-ds-indigo-500 text-[10px] font-semibold tracking-wide shadow-sm max-w-full">
                    <GitBranch className="w-3.5 h-3.5 text-ds-indigo-405 shrink-0" />
                    <span className="truncate max-w-[140px] @sm/chat:max-w-[220px]">{t('chatView.focusLabel', { name: selectedProject.name })}</span>
                    <button
                      type="button"
                      onClick={() => {
                        onProjectSelect(null);
                      }}
                      id="clear-chat-repo-focus-btn"
                      className="hover:text-ds-indigo-850 transition-colors ml-1 p-0.5 rounded"
                      title={t('chatView.clearContextTitle')}
                    >
                      <X className="w-2.5 h-2.5" />
                    </button>
                  </div>
                )}

                {selectedSource && (
                  <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-sm bg-ds-blue-500/10 border border-ds-blue-500/20 text-ds-blue-500 text-[10px] font-semibold tracking-wide shadow-sm max-w-full">
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
                  <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-sm bg-ds-emerald-500/10 border border-ds-emerald-500/20 text-ds-emerald-500 text-[10px] font-semibold tracking-wide shadow-sm max-w-full">
                    <Code className="w-3 h-3 text-ds-emerald-400 shrink-0" />
                    <span className="truncate max-w-[140px] @sm/chat:max-w-[220px]" title={pinnedCode.context || `${pinnedCode.filepath}:${pinnedCode.line}`}>
                      {t('chatView.pinLabel', { path: pinnedCode.label || `${pinnedCode.filepath.split('/').pop()}:${pinnedCode.line}` })}
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
              rows={1}
              id="chat-textarea"
              className={cn(
                "min-h-[36px] max-h-20 w-full bg-transparent border-0 focus:ring-0 focus:outline-none focus-visible:ring-0 focus-visible:outline-none px-3 pt-2 pb-1.5 resize-none text-[13px] outline-none overflow-y-auto",
                theme === 'dark' ? "text-ds-zinc-100 placeholder:text-ds-zinc-650" : "text-ds-zinc-900 placeholder:text-ds-zinc-400"
              )}
              placeholder={t('chatView.inputPlaceholder')}
              value={currentMessage}
              onChange={(e) => {
                setCurrentMessage(e.target.value);
                // Grow with content up to max-h-20 (80px, ~4 lines), then scroll
                // internally instead of pushing the message history out of view —
                // this pane can be one of 4 simultaneously open views (quarter-grid
                // layout), where height is the scarce resource, not just width.
                e.target.style.height = 'auto';
                e.target.style.height = `${Math.min(e.target.scrollHeight, 80)}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendChat();
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
                      <DropdownMenuLabel className="text-[9px] font-bold uppercase tracking-wider text-ds-zinc-500">
                        {selectedProject ? t('chatView.sourcesForProject', { name: selectedProject.name }) : t('chatView.globalSources')}
                      </DropdownMenuLabel>
                      <DropdownMenuItem className="text-xs gap-2" onClick={() => handleSourceFocusChange(null)}>
                        <Check className={cn("w-3.5 h-3.5 shrink-0", !selectedSource ? "opacity-100" : "opacity-0")} />
                        {t('chatView.noKnowledgeSource')}
                      </DropdownMenuItem>
                      {filteredSources && filteredSources.length > 0 ? (
                        filteredSources.map((src: any) => (
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

                  <Select
                    value={activeProfileId}
                    onValueChange={(val) => {
                      setActiveProfileId(val);
                      localStorage.setItem('doctus-active-profile-id', val);
                      const selectedProf = llmProfiles.find(p => p.id === val);
                      if (selectedProf) {
                        showToast(t('chatView.modelSwitchedToast', { name: selectedProf.name }), "success");
                      }
                    }}
                  >
                    <SelectTrigger aria-label={t('chatView.selectModel')} className={cn(
                      "h-7 w-7 @sm/chat:w-auto @sm/chat:max-w-[160px] @sm/chat:min-w-[110px] text-xs border focus:ring-0 shrink-0 rounded-lg font-medium shadow-sm transition-all flex items-center justify-center @sm/chat:justify-between gap-1 px-0 @sm/chat:px-2.5",
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
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Button
                    variant="ghost"
                    size="icon"
                    id="chat-action-share-btn"
                    title={t('chatView.shareChatTitle')}
                    className={cn("h-7 w-7 rounded-full", theme === 'dark' ? "text-ds-zinc-500 hover:text-ds-zinc-300 hover:bg-ds-zinc-800" : "text-ds-zinc-500 hover:text-ds-zinc-800 hover:bg-ds-zinc-100")}
                    onClick={async () => {
                      if (activeSessionId) {
                          const url = window.location.href;
                          const success = await copyToClipboard(url);
                          if (success) {
                              showToast(t('chatView.linkCopiedToast'), "success");
                          } else {
                              showToast(t('chatView.copyFailedToast'), "error");
                          }
                      } else {
                          showToast(t('chatView.startChatFirstToast'), "error");
                      }
                    }}
                  >
                      <Share2 className="w-3.5 h-3.5" />
                  </Button>
               </div>
               <Button
                  size="icon"
                  id="send-chat-message-btn"
                  aria-label={t('chatView.sendMessageLabel')}
                  disabled={isLoading || !currentMessage.trim()}
                  onClick={() => handleSendChat()}
                  className={cn(
                      "h-8 w-8 rounded-lg transition-all font-semibold",
                      currentMessage.trim()
                        ? (theme === 'dark'
                            ? "bg-ds-zinc-100 text-ds-zinc-900 hover:bg-ds-white shadow-lg shadow-ds-white/10"
                            : "bg-transparent text-ds-zinc-900 hover:bg-ds-indigo-650 hover:text-ds-white hover:shadow-lg hover:shadow-ds-indigo-655/20")
                        : (theme === 'dark'
                            ? "bg-ds-zinc-800 text-ds-zinc-650 opacity-50 cursor-not-allowed"
                            : "bg-ds-zinc-100 text-ds-zinc-400 opacity-50 cursor-not-allowed")
                  )}
               >
                  <Send className="w-3.5 h-3.5" />
               </Button>
            </div>
          </div>
          {/* AI Warning Disclaimer */}
          <div className="mt-1 text-[8px] leading-tight text-ds-zinc-650 text-center font-bold tracking-wider uppercase px-3">
            {t('chatView.aiDisclaimer')}
          </div>
        </div>
      </div>
    </div>
  );
}
