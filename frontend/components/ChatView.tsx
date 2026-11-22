"use client";
import type { ShowToast } from './Toast';
import type { LlmProfile } from '@/hooks/useAiSettings';
import type { ChatPinnedFocus } from '@/lib/chatFocus';
import type { AgentCallGraphViewAction, AgentCodeViewAction, AgentDocumentViewAction, AgentGraphViewAction, AgentStep, AgentViewAction, AgentViewActionStatus, AgentWalkthroughViewAction, ChatMessage, ChatMetadata, ChatAttachment, ChatControls, FeedbackReason, KnowledgeSource, Project, WorkspaceDocument } from '@/types/domain';
import type { CallFlowData } from '@/lib/callFlow';
import { extractCallFlowData, extractChangeImpactData } from '@/lib/callFlow';
import { api } from '@/app/services/api';
import { DoctusIcon } from "@/components/Logo";
import { RevealedMarkdown } from "@/components/RevealedMarkdown";
import { useChatFollowScroll } from "@/hooks/useChatFollowScroll";
import { ProvenanceDisclosure } from "@/components/ProvenanceDisclosure";
import { ChatMessageActions } from '@/components/ChatMessageActions';
import { ChatReviewedSource } from '@/components/ChatReviewedSource';
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger
} from "@/components/ui/select";
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { getEdgeTypeLabel } from '@/lib/graphTaxonomy';
import { cn } from "@/lib/utils";
import {
  ArrowRight,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  Code,
  Cpu,
  Database,
  Folder,
  GitBranch,
  History,
  Loader2,
  Pencil,
  FileText,
  ArrowDown,
  Plus,
  Play,
  Search,
  Send,
  Sparkles,
  X
} from 'lucide-react';
import Image from 'next/image';
import React from 'react';
import { AgentSteps, HistoryCompactedNotice } from "./AgentSteps";
import { ChatComposer } from "./ChatComposer";
import { ChatQuestionEditor } from "./ChatQuestionEditor";
import { ChatEmptyState } from "./ChatEmptyState";
import { lockedChatMode } from "@/lib/chatMode";

interface ChatViewProps {
  theme: string;
  isSidebarOpen: boolean;
  selectedProject: Project | null;
  onProjectSelect: (project: Project | null) => void | Promise<void>;
  pinnedCode: ChatPinnedFocus | null;
  setPinnedCode: (code: ChatPinnedFocus | null) => void;
  chatMessages: ChatMessage[];
  currentMessage: string;
  setCurrentMessage: (msg: string) => void;
  isLoading: boolean;
  handleSendChat: (overrideMsg?: string, extraMetadata?: ChatMetadata, attachments?: ChatAttachment[]) => void;
  chatMode?: 'normal' | 'evidence';
  setChatMode?: (mode: 'normal' | 'evidence') => void;
  handleRetryMessage: (index: number) => void;
  chatControls?: ChatControls;
  handleFeedback: (messageId: number, feedback: 'up' | 'down', reason?: FeedbackReason, comment?: string) => void;
  addAssistantHint: (text: string) => void;
  handleFileSelect: (path: string, line?: number, sourceId?: string) => void;
  activeProfileId: string;
  setActiveProfileId: (val: string) => void;
  llmProfiles: LlmProfile[];
  showToast: ShowToast;
  selectedFile: string | null;
  selectedDoc: WorkspaceDocument | null;
  splitClasses: { chat: string; editor: string };
  chatEndRef: React.RefObject<HTMLDivElement>;
  selectedSource: KnowledgeSource | null;
  setSelectedSource: (source: KnowledgeSource | null) => void;
  connectedSources: KnowledgeSource[];
  onOpenCallFlow?: (flow: CallFlowData) => boolean;
  onApplyAgentViewAction?: (action: AgentViewAction, flow?: CallFlowData) => Exclude<AgentViewActionStatus, 'requested'>;
  onAgentViewActionOutcome?: (actionId: string, status: Exclude<AgentViewActionStatus, 'requested'>) => void;
}

/** Renders a `[start, end]` line pair as "43" for a single line, "43-50" otherwise. */
function formatLineRange(lines?: Array<number | null> | null): string {
  const [start, end] = lines ?? [];
  if (start == null) return '';
  if (end == null || end === start) return String(start);
  return `${start}-${end}`;
}

// Historical messages can contain one view proposal for every tool read. They
// remain valid metadata, but the chat no longer renders those noisy controls.
const legacyViewPromptsEnabled = false;

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
  handleSendChat,
  chatMode = 'evidence',
  setChatMode,
  handleRetryMessage,
  chatControls,
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
  connectedSources,
  onOpenCallFlow,
  onApplyAgentViewAction,
  onAgentViewActionOutcome,
}: ChatViewProps) {
  const { t } = useLanguage();
  const sessionChatMode = lockedChatMode(chatMessages);
  const activeChatMode = sessionChatMode ?? chatMode;
  // Mitscrollen bis höchstens zur letzten Frage, damit eine lange Antwort von ihrem Anfang an lesbar bleibt.
  const messageStreamRef = React.useRef<HTMLDivElement>(null);
  const { following: followingLatest, scrollToLatest } = useChatFollowScroll(messageStreamRef, chatMessages.length);
  const olderMessages = chatControls?.olderMessages;
  // Bearbeiten der letzten Frage direkt in ihrer Blase (Pfeil hoch im leeren Feld oder Stift neben der Frage).
  const [editingIndex, setEditingIndex] = React.useState<number | null>(null);
  const lastUserIndex = chatMessages.map(message => message.role).lastIndexOf('user');
  const canEditLast = !isLoading && lastUserIndex >= 0 && chatMessages[lastUserIndex]?.id != null && Boolean(chatControls);
  const startEditLast = () => { if (canEditLast) setEditingIndex(lastUserIndex); };
  React.useEffect(() => {
    if (!isLoading || !chatControls) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') chatControls.stop(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isLoading, chatControls]);
  const anchorIndex = chatMessages.map(message => message.role).lastIndexOf('user');
  // Die Antwort der laufenden Anfrage wird eingeblendet. Gemerkt wird sie, solange die Anfrage läuft,
  // denn eine Antwort am Stück kommt oft im selben Moment wie das Ende der Anfrage. Ein anderer
  // Verlauf (anderes erstes Element) hebt die Markierung auf.
  const [liveTurn, setLiveTurn] = React.useState<{ index: number; first: ChatMessage | undefined } | null>(null);
  if (isLoading && chatMessages.length > 0
    && (liveTurn?.index !== chatMessages.length - 1 || liveTurn.first !== chatMessages[0])) {
    setLiveTurn({ index: chatMessages.length - 1, first: chatMessages[0] });
  }
  const liveIndex = liveTurn && liveTurn.first === chatMessages[0] ? liveTurn.index : -1;

  const [originalAnswers, setOriginalAnswers] = React.useState<Set<number | string>>(() => new Set());
  // Angezeigte Fassung je wiederholter Antwort (Index in metadata.versions); ohne Eintrag die aktuelle.
  const [versionView, setVersionView] = React.useState<Record<number, number>>({});
  const versionOf = (m: ChatMessage) => {
    const versions = m.metadata?.versions ?? [];
    const index = m.id != null ? versionView[m.id] : undefined;
    return index != null && index < versions.length
      ? { index, content: versions[index].content }
      : { index: versions.length, content: m.content };
  };
  const [callFlowDecisions, setCallFlowDecisions] = React.useState<Record<string, 'open' | 'declined'>>({});
  const handleOpenFlow = (flow: CallFlowData, key: string | number, action?: AgentViewAction) => {
    const outcome = action
      ? onApplyAgentViewAction?.(action, flow) ?? 'rejected'
      : onOpenCallFlow?.(flow) ? 'opened' : 'no_space';
    if (action) onAgentViewActionOutcome?.(action.action_id, outcome);
    if (outcome === 'opened' || outcome === 'updated') {
      setCallFlowDecisions(previous => ({ ...previous, [String(key)]: 'open' }));
    }
  };
  const handleOpenCodeLocation = (action: AgentViewAction) => {
    if (action.view !== 'code' || !onApplyAgentViewAction) return;
    onAgentViewActionOutcome?.(action.action_id, onApplyAgentViewAction(action));
  };
  const handleOpenGraphNeighborhood = (action: AgentViewAction) => {
    if (action.view !== 'graph' || !onApplyAgentViewAction) return;
    onAgentViewActionOutcome?.(action.action_id, onApplyAgentViewAction(action));
  };
  const handleDeclineViewAction = (action: AgentViewAction) => {
    onAgentViewActionOutcome?.(action.action_id, 'declined');
  };
  const [walkthroughProgress, setWalkthroughProgress] = React.useState<Record<string, number | null>>({});
  const openWalkthroughStep = (action: AgentWalkthroughViewAction, stepIndex: number, agentSteps?: AgentStep[]) => {
    const step = action.target.steps[stepIndex];
    if (!step || !onApplyAgentViewAction) return;
    let outcome: Exclude<AgentViewActionStatus, 'requested'>;
    if (step.kind === 'callgraph') {
      const traceResult = agentSteps?.find((candidate): candidate is Extract<AgentStep, { type: 'tool_result' }> =>
        candidate.type === 'tool_result' && candidate.name === 'trace_call_flow' && candidate.id === step.trace_tool_call_id,
      );
      const flow = traceResult
        ? extractCallFlowData({ role: 'assistant', content: '', metadata: { agent_steps: [traceResult] } })
        : null;
      const edge = flow?.edges.find(candidate => candidate.id === step.edge_id);
      if (!flow || !edge || edge.resolution !== 'resolved' || edge.source !== step.source_entity_id || edge.target !== step.target_entity_id) return;
      const stepAction: AgentCallGraphViewAction = {
        ...action,
        tool_call_id: step.trace_tool_call_id,
        view: 'callgraph',
        target: {
          entity_id: flow.root.id,
          focus_entity_id: step.target_entity_id,
          highlighted_edge_id: step.edge_id,
        },
      };
      outcome = onApplyAgentViewAction(stepAction, {
        ...flow,
        focus_entity_id: step.target_entity_id,
        highlighted_edge_id: step.edge_id,
      });
    } else {
      const stepAction: AgentCodeViewAction | AgentDocumentViewAction = step.kind === 'document'
        ? { ...action, view: 'document', target: step }
        : { ...action, view: 'code', target: step };
      outcome = onApplyAgentViewAction(stepAction);
    }
    onAgentViewActionOutcome?.(action.action_id, outcome);
    if (outcome === 'opened' || outcome === 'updated') {
      setWalkthroughProgress(previous => ({ ...previous, [action.action_id]: stepIndex }));
    }
  };

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

  const handleSourceFocusChange = (source: KnowledgeSource | null) => {
    setSelectedSource(source);
  };

  return (
    <div className={cn(
      "@container/chat h-full flex flex-col transition-all duration-300 ease-in-out relative",
      (selectedFile || selectedDoc) ? splitClasses.chat : "w-full"
    )}>

      {sessionChatMode === null && (
      <div className="flex shrink-0 justify-center px-4 pt-2 @sm/chat:px-6">
        <div role="group" aria-label={t('chatView.modeLabel')} className={cn(
          "flex items-center rounded-full border p-1 shadow-sm",
          theme === 'dark' ? 'border-ds-zinc-700 bg-ds-zinc-900' : 'border-ds-zinc-200 bg-ds-white'
        )}>
          {(['normal', 'evidence'] as const).map(mode => (
            <button key={mode} type="button" aria-pressed={chatMode === mode} disabled={isLoading}
              onClick={() => setChatMode?.(mode)} title={t(`chatView.mode.${mode}Description`)}
              className={cn('rounded-full px-3 py-1 text-xs font-semibold transition-colors disabled:opacity-60', chatMode === mode
                // Nur die ds-Variante existiert im Tailwind-Theme (colors ersetzt die Defaults),
                // die Beschriftung erbte daher die dunkle Textfarbe.
                ? 'bg-ds-indigo-600 text-ds-white'
                : 'text-ds-zinc-500 hover:text-ds-zinc-200')}>
              {t(`chatView.mode.${mode}`)}
            </button>
          ))}
        </div>
      </div>
      )}

      {/* Chat message stream container */}
      <ScrollArea className="flex-1 w-full min-w-0">
        <div ref={messageStreamRef} className={cn(
          "w-full px-4 @sm/chat:px-6 pt-3 pb-6 @sm/chat:pb-8 flex flex-col min-h-full justify-between mx-auto",
          chatMessages.length === 0 ? "max-w-7xl" : "max-w-4xl"
        )}>

          {/* Zero State / Welcomer */}
          {chatMessages.length === 0 ? (
            <ChatEmptyState
              theme={theme}
              chatMode={chatMode}
              selectedProject={selectedProject}
              onSend={handleSendChat}
              onFillMessage={setCurrentMessage}
              addAssistantHint={addAssistantHint}
              showToast={showToast}
            />
          ) : (
            // Message Stream
            <div className="space-y-6 pb-6">
              {olderMessages?.hasMore && (
                <div className="flex justify-center">
                  <Button variant="ghost" size="sm" disabled={olderMessages.loading || isLoading} onClick={() => void olderMessages.load()}
                    className="h-7 text-xs text-ds-zinc-500">{t(olderMessages.loading ? 'chatView.loadingOlderMessages' : 'chatView.loadOlderMessages')}</Button>
                </div>
              )}
              {chatMessages.map((m, i) => {
                const isUser = m.role === 'user';
                return (
                  <div
                    key={i}
                    data-chat-anchor={i === anchorIndex ? 'true' : undefined}
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
                      isUser && "relative group/question",
                      isUser
                        ? (theme === 'dark'
                            ? "bg-ds-zinc-900/95 border border-ds-zinc-800/80 text-ds-zinc-100 rounded-lg px-5 py-3 shadow-lg"
                            : "bg-ds-white border border-ds-zinc-200 text-ds-zinc-900 rounded-lg px-5 py-3 shadow-md shadow-ds-zinc-100")
                        : (theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-800")
                    )}>
                      {isUser ? (
                        <>
                          {m.metadata && Boolean(m.metadata.project || m.metadata.pinned || m.metadata.refs?.length || m.metadata.attachments?.length) && (
                            <div className="flex flex-wrap gap-2 mb-2 pb-2 border-b border-ds-zinc-200/50 dark:border-ds-zinc-800/50">
                              {m.metadata.project && (
                                <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-ds-indigo-500/10 border border-ds-indigo-500/20 text-[0.625rem] text-ds-indigo-400 font-bold uppercase tracking-tight">
                                  <Database className="w-3 h-3" />
                                  {m.metadata.project.name}
                                </div>
                              )}
                              {m.metadata.attachments?.map(item => (
                                <div key={item.name} title={t('chatView.attachmentSize', { count: item.chars })}
                                  className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-ds-zinc-500/10 border border-ds-zinc-500/20 text-[0.625rem] text-ds-zinc-400 font-bold">
                                  <FileText className="w-3 h-3" />
                                  {item.name}
                                </div>
                              ))}
                              {(m.metadata.refs?.length ? m.metadata.refs : (m.metadata.pinned ? [{
                                file: m.metadata.pinned.filepath || '',
                                line: m.metadata.pinned.line ?? 0,
                                label: m.metadata.pinned.label,
                                source_id: m.metadata.pinned.source_id
                              }] : [])).map((ref, refIndex) => {
                                const pinned = m.metadata?.focus?.pinned || m.metadata?.pinned;
                                const location = `${ref.file.split('/').pop()}:${ref.line}`;
                                const rawLabel = ref.label || (
                                  pinned?.filepath === ref.file && pinned?.line === ref.line
                                    ? (pinned?.breadcrumb || pinned?.label)
                                    : null
                                );
                                // A bare gutter-line pin (no enclosing entity) sets its label to
                                // this same "file:line" text (handleGutterClick) — showing it next
                                // to `location` would just repeat it twice.
                                const label = rawLabel && rawLabel !== location ? rawLabel : null;
                                return (
                                <button
                                  type="button"
                                  onClick={() => handleFileSelect(
                                    ref.file,
                                    ref.line,
                                    ref.source_id ? String(ref.source_id) : undefined
                                  )}
                                  key={`${ref.file}:${ref.line}:${refIndex}`}
                                  className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-ds-emerald-500/10 border border-ds-emerald-500/20 text-[0.625rem] text-ds-emerald-400 hover:bg-ds-emerald-500/20 hover:border-ds-emerald-500/40 font-bold uppercase tracking-tight transition-colors cursor-pointer"
                                  title={label
                                    ? `${label} · ${t('chatView.openPinnedLineTitle', { path: ref.file, line: ref.line })}`
                                    : t('chatView.openPinnedLineTitle', { path: ref.file, line: ref.line })}
                                >
                                  <Code className="w-3 h-3" />
                                  {label ? `${label} · ${location}` : location}
                                </button>
                                );
                              })}
                            </div>
                          )}
                          {editingIndex === i ? (
                            <ChatQuestionEditor initial={m.content} theme={theme} onCancel={() => setEditingIndex(null)}
                              onSubmit={(text) => { setEditingIndex(null); void chatControls?.editLast(text); }} />
                          ) : (
                            <p className="whitespace-pre-wrap font-medium">{m.content}</p>
                          )}
                          {i === lastUserIndex && canEditLast && editingIndex !== i && (
                            <Button variant="ghost" size="icon" onClick={startEditLast} title={t('chatView.editQuestionTitle')} aria-label={t('chatView.editQuestion')}
                              className={cn("absolute -left-9 bottom-0 h-7 w-7 rounded-full opacity-0 group-hover/question:opacity-100 focus-visible:opacity-100 transition-opacity",
                                theme === 'dark' ? "text-ds-zinc-500 hover:text-ds-zinc-300 hover:bg-ds-zinc-800" : "text-ds-zinc-500 hover:text-ds-zinc-800 hover:bg-ds-zinc-100")}>
                              <Pencil className="w-3.5 h-3.5" />
                            </Button>
                          )}
                        </>
                      ) : (
                        <>
                          {m.metadata?.agent_steps && <HistoryCompactedNotice steps={m.metadata.agent_steps} />}
                          {m.metadata && m.metadata.agent_steps && m.metadata.agent_steps.length > 0 && (
                            <AgentSteps steps={m.metadata.agent_steps.filter(step => step.type !== 'view_action')} theme={theme} isLive={isLoading && !m.id} />
                          )}

                          {m.content ? (
                            <RevealedMarkdown live={i === liveIndex} content={versionOf(m).content} compactCitations={!originalAnswers.has(m.id ?? `index:${i}`)} onFileClick={handleFileSelect} theme={theme} knownSources={m.sources?.filter(source => !source.kind)} />
                          ) : (
                            isLoading && i === chatMessages.length - 1 && (!m.metadata?.agent_steps || m.metadata.agent_steps.length === 0) && (
                              <div className="flex items-center gap-2.5 text-ds-zinc-500/80 py-1.5 animate-pulse">
                                <Loader2 className="w-4 h-4 animate-spin text-ds-indigo-500 shrink-0" />
                                <span className="text-xs font-medium tracking-wide">
                                  {t(m.metadata?.chat_mode === 'evidence' ? 'chatView.searchingEvidence' : 'chatView.generatingResponse')}
                                </span>
                              </div>
                            )
                          )}

                          {m.metadata?.chat_mode === 'evidence' && m.content && (!isLoading || i !== chatMessages.length - 1) && (
                            <ProvenanceDisclosure
                              theme={theme}
                              variant="dialog"
                              className="mt-2"
                              provenance={{
                                kind: 'model_inference',
                                verification_status: 'unverified',
                                verification_note: t('provenance.answerNote'),
                              }}
                            />
                          )}

                          {isLoading && i === chatMessages.length - 1 && (m.content || (m.metadata?.agent_steps && m.metadata.agent_steps.length > 0)) && (
                            <div className="flex items-center gap-2 text-ds-zinc-500/70 mt-3 py-1 font-medium select-none animate-pulse">
                              <Loader2 className="w-3.5 h-3.5 animate-spin text-ds-indigo-500 shrink-0" />
                              <span className="text-[0.6875rem] italic">{t('chatView.agentWorking')}</span>
                            </div>
                          )}

                          {/* Call Graph Prompt Card if an execution trace was produced */}
                          {(() => {
                            const callFlow = extractCallFlowData(m);
                            if (!callFlow) return null;
                            const decisionKey = m.id ?? i;
                            const viewAction = m.metadata?.agent_steps?.find((step): step is AgentCallGraphViewAction =>
                              step.type === 'view_action' && step.view === 'callgraph' && step.target.entity_id === callFlow.root.id
                            );
                            const actionOpened = viewAction?.type === 'view_action' &&
                              (viewAction.status === 'opened' || viewAction.status === 'updated');
                            const actionDeclined = viewAction?.type === 'view_action' && viewAction.status === 'declined';
                            const actionUnavailable = viewAction?.type === 'view_action' &&
                              (viewAction.status === 'rejected' || viewAction.status === 'stale_context');
                            const decision = callFlowDecisions[decisionKey] ?? (actionOpened ? 'open' : actionDeclined ? 'declined' : undefined);

                            if (actionUnavailable) {
                              return (
                                <div className="mt-3 px-3 py-2 rounded-lg border border-ds-amber-500/30 bg-ds-amber-500/5 text-[0.6875rem] text-ds-amber-500">
                                  {t('chatView.agentViewUnavailable')}
                                </div>
                              );
                            }

                            if (decision === 'declined') {
                              return (
                                <div className="mt-2.5 flex items-center gap-2">
                                  <button
                                    type="button"
                                    onClick={() => handleOpenFlow(callFlow, decisionKey, viewAction)}
                                    className="inline-flex items-center gap-1.5 text-[0.6875rem] font-medium text-ds-zinc-500 hover:text-ds-indigo-500 transition-colors cursor-pointer"
                                    title={t('chatView.callGraphReopen')}
                                  >
                                    <GitBranch className="w-3.5 h-3.5 text-ds-indigo-500" />
                                    <span>{t('chatView.callGraphReopen')}</span>
                                  </button>
                                </div>
                              );
                            }

                            if (decision === 'open') {
                              return (
                                <div className={cn(
                                  "mt-3 px-3 py-2 rounded-lg border flex items-center justify-between gap-2 text-xs",
                                  theme === 'dark' ? "bg-ds-zinc-900/40 border-ds-zinc-800 text-ds-zinc-400" : "bg-ds-zinc-100/60 border-ds-zinc-200 text-ds-zinc-600"
                                )}>
                                  <div className="flex items-center gap-2">
                                    <Check className="w-3.5 h-3.5 text-ds-emerald-500" />
                                    <span className="font-medium text-ds-zinc-300">{t('chatView.callGraphOpened')} ({callFlow.root.name})</span>
                                  </div>
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => handleOpenFlow(callFlow, decisionKey, viewAction)}
                                    className="h-6 px-2 text-[0.6875rem] text-ds-indigo-400 hover:text-ds-indigo-300 cursor-pointer"
                                  >
                                    {t('chatView.callGraphReopen')}
                                  </Button>
                                </div>
                              );
                            }

                            return (
                              <div
                                data-testid="callgraph-prompt-card"
                                className={cn(
                                  "mt-3.5 p-3 rounded-lg border flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm transition-all",
                                  theme === 'dark'
                                    ? "bg-ds-indigo-950/20 border-ds-indigo-500/30 text-ds-zinc-200"
                                    : "bg-ds-indigo-50/60 border-ds-indigo-200 text-ds-zinc-800"
                                )}
                              >
                                <div className="flex items-center gap-2.5 min-w-0">
                                  <div className={cn(
                                    "p-1.5 rounded-md border shrink-0",
                                    theme === 'dark' ? "bg-ds-indigo-950/60 border-ds-indigo-500/30 text-ds-indigo-400" : "bg-ds-indigo-100 border-ds-indigo-200 text-ds-indigo-600"
                                  )}>
                                    <GitBranch className="w-4 h-4" />
                                  </div>
                                  <div className="min-w-0">
                                    <p className="text-xs font-semibold tracking-tight">
                                      {t('chatView.callGraphPrompt')}
                                    </p>
                                    <p className="text-[0.625rem] text-ds-zinc-500 truncate">
                                      {callFlow.root.name} · {callFlow.hops} {callFlow.hops !== 1 ? t('callGraphView.hopUnitPlural') : t('callGraphView.hopUnit')} ({callFlow.nodes.length} Knoten)
                                    </p>
                                    {viewAction?.type === 'view_action' && viewAction.status === 'no_space' && (
                                      <p className="text-[0.625rem] text-ds-amber-500 mt-1">{t('chatView.callGraphNoSpace')}</p>
                                    )}
                                  </div>
                                </div>
                                <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="ghost"
                                    id={`chat-callgraph-decline-btn-${i}`}
                                    onClick={() => {
                                      setCallFlowDecisions((prev) => ({ ...prev, [String(decisionKey)]: 'declined' }));
                                      if (viewAction?.type === 'view_action') handleDeclineViewAction(viewAction);
                                    }}
                                    className="h-7 px-3 text-xs text-ds-zinc-500 hover:text-ds-zinc-700 dark:hover:text-ds-zinc-300 cursor-pointer"
                                  >
                                    {t('chatView.callGraphDismissButton')}
                                  </Button>
                                  <Button
                                    type="button"
                                    size="sm"
                                    id={`chat-callgraph-open-btn-${i}`}
                                    onClick={() => handleOpenFlow(callFlow, decisionKey, viewAction)}
                                    className="h-7 px-3 text-xs font-semibold bg-ds-indigo-600 hover:bg-ds-indigo-500 text-ds-white shadow-sm cursor-pointer"
                                  >
                                    <GitBranch className="w-3.5 h-3.5 mr-1.5" />
                                    {t('chatView.callGraphInvestigateButton')}
                                  </Button>
                                </div>
                              </div>
                            );
                          })()}

                          {/* Bounded change-impact summary with an explicit graph action. */}
                          {(() => {
                            const impact = extractChangeImpactData(m);
                            if (!impact) return null;
                            const viewAction = m.metadata?.agent_steps?.find((step): step is AgentCallGraphViewAction =>
                              step.type === 'view_action' && step.view === 'callgraph' &&
                              step.tool_call_id === impact.toolCallId && step.target.entity_id === impact.flow.root.id
                            );
                            if (!viewAction) return null;
                            const decisionKey = impact.toolCallId;
                            const actionOpened = viewAction.status === 'opened' || viewAction.status === 'updated';
                            const actionDeclined = viewAction.status === 'declined';
                            const actionUnavailable = viewAction.status === 'rejected' || viewAction.status === 'stale_context';
                            const decision = callFlowDecisions[decisionKey] ?? (actionOpened ? 'open' : actionDeclined ? 'declined' : undefined);
                            return (
                              <div
                                data-testid="change-impact-card"
                                className={cn(
                                  "mt-3.5 p-3 rounded-lg border flex flex-col gap-2.5 shadow-sm",
                                  theme === 'dark'
                                    ? "bg-ds-indigo-950/20 border-ds-indigo-500/30 text-ds-zinc-200"
                                    : "bg-ds-indigo-50/60 border-ds-indigo-200 text-ds-zinc-800"
                                )}
                              >
                                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                                  <div className="min-w-0">
                                    <p className="text-xs font-semibold">{t('chatView.changeImpactTitle')}</p>
                                    <p className="text-[0.6875rem] text-ds-zinc-500 truncate" title={impact.targetLabel}>
                                      {impact.targetLabel} · {t('chatView.changeImpactNodeCount', { count: impact.flow.nodes.length })} · {impact.flow.hops} {impact.flow.hops !== 1 ? t('callGraphView.hopUnitPlural') : t('callGraphView.hopUnit')}
                                    </p>
                                    <p className="text-[0.6875rem] text-ds-zinc-500 mt-1">
                                      {t('chatView.changeImpactCounts', {
                                        resolved: impact.summary.statically_resolved_edges,
                                        heuristic: impact.summary.heuristic_links,
                                        unknown: impact.summary.unknown_dynamic_edges,
                                      })}
                                    </p>
                                    <p className="text-[0.625rem] text-ds-zinc-500 mt-1">{t('chatView.changeImpactLimits')}</p>
                                    {impact.summary.truncated && (
                                      <p className="text-[0.625rem] text-ds-amber-500 mt-1">{t('chatView.changeImpactTruncated')}</p>
                                    )}
                                    {actionUnavailable && (
                                      <p className="text-[0.625rem] text-ds-amber-500 mt-1">{t('chatView.agentViewUnavailable')}</p>
                                    )}
                                    {viewAction.status === 'no_space' && (
                                      <p className="text-[0.625rem] text-ds-amber-500 mt-1">{t('chatView.changeImpactNoSpace')}</p>
                                    )}
                                  </div>
                                  {!actionUnavailable && (
                                    <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                                      {decision !== 'open' && decision !== 'declined' && (
                                        <Button
                                          type="button"
                                          size="sm"
                                          variant="ghost"
                                          onClick={() => {
                                            setCallFlowDecisions(previous => ({ ...previous, [decisionKey]: 'declined' }));
                                            handleDeclineViewAction(viewAction);
                                          }}
                                          className="h-7 px-2 text-xs text-ds-zinc-500 cursor-pointer"
                                        >
                                          {t('chatView.callGraphDismissButton')}
                                        </Button>
                                      )}
                                      <Button
                                        type="button"
                                        size="sm"
                                        onClick={() => handleOpenFlow(impact.flow, decisionKey, viewAction)}
                                        className="h-7 px-3 text-xs font-semibold bg-ds-indigo-600 hover:bg-ds-indigo-500 text-ds-white shadow-sm cursor-pointer"
                                      >
                                        <GitBranch className="w-3.5 h-3.5 mr-1.5" />
                                        {decision === 'open' ? t('chatView.changeImpactReopen') : t('chatView.changeImpactOpenButton')}
                                      </Button>
                                    </div>
                                  )}
                                </div>
                                {decision === 'open' && (
                                  <p className="text-[0.625rem] text-ds-emerald-500">{t('chatView.changeImpactOpened')}</p>
                                )}
                              </div>
                            );
                          })()}

                          {m.metadata?.agent_steps?.filter((step): step is AgentGraphViewAction =>
                            step.type === 'view_action' && step.view === 'graph',
                          ).map((action) => {
                            const isOpen = action.status === 'opened' || action.status === 'updated';
                            const isDeclined = action.status === 'declined';
                            const isUnavailable = action.status === 'rejected' || action.status === 'stale_context';
                            const direction = action.target.direction === 'incoming'
                              ? t('knowledgeGraphView.agentDirectionIncoming')
                              : action.target.direction === 'outgoing'
                                ? t('knowledgeGraphView.agentDirectionOutgoing')
                                : t('knowledgeGraphView.agentDirectionBoth');
                            return (
                              <div
                                key={action.action_id}
                                data-testid={`graph-neighborhood-action-${action.action_id}`}
                                className={cn(
                                  'mt-3.5 p-3 rounded-lg border flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm text-xs',
                                  theme === 'dark'
                                    ? 'bg-ds-indigo-950/20 border-ds-indigo-500/30 text-ds-zinc-200'
                                    : 'bg-ds-indigo-50/60 border-ds-indigo-200 text-ds-zinc-800',
                                )}
                              >
                                <div className="min-w-0">
                                  <p className="text-xs font-semibold tracking-tight">
                                    {isOpen ? t('chatView.graphNeighborhoodOpened') : t('chatView.graphNeighborhoodPrompt')}
                                  </p>
                                  <p className="text-[0.625rem] text-ds-zinc-500 truncate" title={action.target.focus_label}>
                                    {action.target.focus_label} · {direction} · {action.target.relationships
                                      .map(type => getEdgeTypeLabel(type, t))
                                      .join(', ')}
                                  </p>
                                  {action.status === 'no_space' && <p className="text-[0.625rem] text-ds-amber-500 mt-1">{t('chatView.callGraphNoSpace')}</p>}
                                  {isUnavailable && <p className="text-[0.625rem] text-ds-amber-500 mt-1">{t('chatView.agentViewUnavailable')}</p>}
                                </div>
                                {!isUnavailable && (
                                  <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                                    {!isOpen && !isDeclined && (
                                      <Button
                                        type="button"
                                        size="sm"
                                        variant="ghost"
                                        onClick={() => handleDeclineViewAction(action)}
                                        className="h-7 px-2 text-xs text-ds-zinc-500 cursor-pointer"
                                      >
                                        {t('chatView.callGraphDismissButton')}
                                      </Button>
                                    )}
                                    <Button
                                      type="button"
                                      size="sm"
                                      onClick={() => handleOpenGraphNeighborhood(action)}
                                      className="h-7 px-3 text-xs font-semibold bg-ds-indigo-600 hover:bg-ds-indigo-500 text-ds-white shadow-sm cursor-pointer"
                                    >
                                      <GitBranch className="w-3.5 h-3.5 mr-1.5" />
                                      {isOpen || isDeclined ? t('chatView.graphNeighborhoodReopen') : t('chatView.graphNeighborhoodOpenButton')}
                                    </Button>
                                  </div>
                                )}
                              </div>
                            );
                          })}

                          {/* A code location is only offered after view_repo_file returned the bounded location. */}
                          {legacyViewPromptsEnabled && m.metadata?.agent_steps?.filter((step): step is AgentCodeViewAction =>
                            step.type === 'view_action' && step.view === 'code',
                          ).map((action) => {
                            const isOpen = action.status === 'opened' || action.status === 'updated';
                            const isDeclined = action.status === 'declined';
                            const isUnavailable = action.status === 'rejected' || action.status === 'stale_context';
                            const lineRange = action.target.start_line === action.target.end_line
                              ? String(action.target.start_line)
                              : `${action.target.start_line}-${action.target.end_line}`;
                            const location = `${action.target.file_path}:L${lineRange}`;
                            return (
                              <div
                                key={action.action_id}
                                data-testid={`code-location-action-${action.action_id}`}
                                className={cn(
                                  'mt-3.5 p-3 rounded-lg border flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm text-xs',
                                  theme === 'dark'
                                    ? 'bg-ds-indigo-950/20 border-ds-indigo-500/30 text-ds-zinc-200'
                                    : 'bg-ds-indigo-50/60 border-ds-indigo-200 text-ds-zinc-800',
                                )}
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  <div className={cn(
                                    'p-1.5 rounded-md border shrink-0',
                                    theme === 'dark' ? 'bg-ds-indigo-950/60 border-ds-indigo-500/30 text-ds-indigo-400' : 'bg-ds-indigo-100 border-ds-indigo-200 text-ds-indigo-600',
                                  )}>
                                    {isOpen ? <Check className="w-4 h-4" /> : <Code className="w-4 h-4" />}
                                  </div>
                                  <div className="min-w-0">
                                    <p className="text-xs font-semibold tracking-tight">
                                      {isOpen ? t('chatView.codeLocationOpened') : t('chatView.codeLocationPrompt')}
                                    </p>
                                    <p className="text-[0.625rem] text-ds-zinc-500 truncate font-mono">{location}</p>
                                    {action.status === 'no_space' && <p className="text-[0.625rem] text-ds-amber-500 mt-1">{t('chatView.codeLocationNoSpace')}</p>}
                                    {isUnavailable && <p className="text-[0.625rem] text-ds-amber-500 mt-1">{t('chatView.agentViewUnavailable')}</p>}
                                  </div>
                                </div>
                                <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                                  {isUnavailable ? null : isDeclined ? (
                                    <button
                                      type="button"
                                      onClick={() => handleOpenCodeLocation(action)}
                                      className="inline-flex items-center gap-1.5 text-[0.6875rem] font-medium text-ds-zinc-500 hover:text-ds-indigo-500 transition-colors cursor-pointer"
                                    >
                                      <Code className="w-3.5 h-3.5 text-ds-indigo-500" />
                                      <span>{t('chatView.codeLocationReopen')}</span>
                                    </button>
                                  ) : isOpen ? (
                                    <Button
                                      type="button"
                                      size="sm"
                                      variant="ghost"
                                      onClick={() => handleOpenCodeLocation(action)}
                                      className="h-6 px-2 text-[0.6875rem] text-ds-indigo-400 hover:text-ds-indigo-300 cursor-pointer"
                                    >
                                      {t('chatView.codeLocationReopen')}
                                    </Button>
                                  ) : (
                                    <>
                                      <Button
                                        type="button"
                                        size="sm"
                                        variant="ghost"
                                        onClick={() => handleDeclineViewAction(action)}
                                        className="h-7 px-3 text-xs text-ds-zinc-500 hover:text-ds-zinc-700 dark:hover:text-ds-zinc-300 cursor-pointer"
                                      >
                                        {t('chatView.callGraphDismissButton')}
                                      </Button>
                                      <Button
                                        type="button"
                                        size="sm"
                                        onClick={() => handleOpenCodeLocation(action)}
                                        className="h-7 px-3 text-xs font-semibold bg-ds-indigo-600 hover:bg-ds-indigo-500 text-ds-white shadow-sm cursor-pointer"
                                      >
                                        <Code className="w-3.5 h-3.5 mr-1.5" />
                                        {t('chatView.callGraphOpenButton')}
                                      </Button>
                                    </>
                                  )}
                                </div>
                              </div>
                            );
                          })}

                          {m.metadata?.agent_steps?.filter((step): step is AgentWalkthroughViewAction =>
                            step.type === 'view_action' && step.view === 'walkthrough',
                          ).map((action) => {
                            const savedStepIndex = walkthroughProgress[action.action_id];
                            const activeStepIndex = typeof savedStepIndex === 'number' ? savedStepIndex : -1;
                            const isActive = activeStepIndex >= 0;
                            const activeStep = isActive ? action.target.steps[activeStepIndex] : null;
                            const isUnavailable = action.status === 'rejected' || action.status === 'stale_context';
                            const wasStarted = action.status === 'opened' || action.status === 'updated';
                            return (
                              <div
                                key={action.action_id}
                                data-testid={`code-walkthrough-${action.action_id}`}
                                className={cn(
                                  'mt-4 rounded-xl border overflow-hidden shadow-sm',
                                  theme === 'dark'
                                    ? 'bg-ds-indigo-950/20 border-ds-indigo-500/30'
                                    : 'bg-ds-indigo-50/70 border-ds-indigo-200',
                                )}
                              >
                                <div className="p-3.5 flex items-center justify-between gap-3">
                                  <div className="flex items-center gap-2.5 min-w-0">
                                    <div className="p-2 rounded-lg bg-ds-indigo-500/10 text-ds-indigo-500 shrink-0">
                                      <Play className="w-4 h-4" />
                                    </div>
                                    <div className="min-w-0">
                                      <p className={cn(
                                        'text-xs font-semibold truncate',
                                        theme === 'dark' ? 'text-ds-zinc-200' : 'text-ds-zinc-800',
                                      )}>{action.target.title}</p>
                                      <p className="text-[0.625rem] text-ds-zinc-500">
                                        {t('chatView.walkthroughSummary', { count: action.target.steps.length })}
                                      </p>
                                    </div>
                                  </div>
                                  {!isActive && !isUnavailable && (
                                    <Button
                                      type="button"
                                      size="sm"
                                      onClick={() => openWalkthroughStep(action, 0, m.metadata?.agent_steps)}
                                      className="h-8 px-3 text-xs font-semibold bg-ds-indigo-600 hover:bg-ds-indigo-500 text-ds-white shrink-0 cursor-pointer"
                                    >
                                      <Play className="w-3.5 h-3.5 mr-1.5" />
                                      {wasStarted ? t('chatView.walkthroughRepeat') : t('chatView.walkthroughStart')}
                                    </Button>
                                  )}
                                </div>

                                {isUnavailable && (
                                  <p className="px-3.5 pb-3 text-[0.625rem] text-ds-amber-500">{t('chatView.agentViewUnavailable')}</p>
                                )}

                                {activeStep && (
                                  <div className={cn(
                                    'border-t px-3.5 py-3',
                                    theme === 'dark' ? 'border-ds-indigo-500/20 bg-ds-zinc-950/25' : 'border-ds-indigo-200 bg-ds-white/60',
                                  )}>
                                    <div className="flex items-center justify-between gap-3 mb-2">
                                      <span className="text-[0.625rem] font-bold uppercase tracking-wider text-ds-indigo-400">
                                        {t('chatView.walkthroughStep', { current: activeStepIndex + 1, count: action.target.steps.length })}
                                      </span>
                                      <span className="font-mono text-[0.625rem] text-ds-zinc-500 truncate">
                                        {activeStep.kind === 'callgraph'
                                          ? `${activeStep.source_name} → ${activeStep.target_name}${activeStep.file_path ? ` · ${activeStep.file_path}${activeStep.start_line ? `:L${activeStep.start_line}` : ''}` : ''}`
                                          : `${activeStep.file_path}${activeStep.kind === 'document'
                                            ? activeStep.page ? ` · ${t('chatView.walkthroughPage', { page: activeStep.page })}` : activeStep.section ? ` · ${activeStep.section}` : ''
                                            : `:L${activeStep.start_line}`}`}
                                      </span>
                                    </div>
                                    <p className={cn(
                                      'text-xs leading-relaxed',
                                      theme === 'dark' ? 'text-ds-zinc-300' : 'text-ds-zinc-700',
                                    )}>{activeStep.explanation}</p>
                                    {activeStep.kind === 'document' && activeStep.excerpt && (
                                      <blockquote className={cn(
                                        'mt-2 border-l-2 border-ds-indigo-500/50 pl-3 text-[0.6875rem] leading-relaxed line-clamp-4',
                                        theme === 'dark' ? 'text-ds-zinc-400' : 'text-ds-zinc-600',
                                      )}>
                                        {activeStep.excerpt}
                                      </blockquote>
                                    )}
                                    <div className="mt-3 flex items-center justify-between">
                                      <Button
                                        type="button"
                                        size="sm"
                                        variant="ghost"
                                        disabled={activeStepIndex === 0}
                                        onClick={() => openWalkthroughStep(action, activeStepIndex - 1, m.metadata?.agent_steps)}
                                        className="h-7 px-2 text-xs cursor-pointer"
                                      >
                                        <ChevronLeft className="w-3.5 h-3.5 mr-1" />
                                        {t('chatView.walkthroughBack')}
                                      </Button>
                                      {activeStepIndex < action.target.steps.length - 1 ? (
                                        <Button
                                          type="button"
                                          size="sm"
                                          onClick={() => openWalkthroughStep(action, activeStepIndex + 1, m.metadata?.agent_steps)}
                                          className="h-7 px-3 text-xs bg-ds-indigo-600 hover:bg-ds-indigo-500 text-ds-white cursor-pointer"
                                        >
                                          {t('chatView.walkthroughNext')}
                                          <ChevronRight className="w-3.5 h-3.5 ml-1" />
                                        </Button>
                                      ) : (
                                        <Button
                                          type="button"
                                          size="sm"
                                          onClick={() => setWalkthroughProgress(previous => ({ ...previous, [action.action_id]: null }))}
                                          className="h-7 px-3 text-xs bg-ds-emerald-600 hover:bg-ds-emerald-500 text-ds-white cursor-pointer"
                                        >
                                          {t('chatView.walkthroughFinish')}
                                        </Button>
                                      )}
                                    </div>
                                  </div>
                                )}
                              </div>
                            );
                          })}

                          {/* Sources display if returned from query context */}
                          {m.sources && m.sources.length > 0 && (!isLoading || i !== chatMessages.length - 1) && (
                            <div className={cn(
                              "mt-4 pt-3 border-t flex flex-wrap gap-2 items-center transition-colors",
                              theme === 'dark' ? "border-ds-zinc-800/50" : "border-ds-zinc-200"
                            )}>
                              <span className="text-[0.625rem] text-ds-zinc-500 font-bold uppercase tracking-wider">{t('chatView.referencedSources')}</span>
                              {m.sources.map((src, sIdx) => {
                                if (src.kind === 'insight' || src.kind === 'ci_build') return <ChatReviewedSource key={`${src.kind}-${src.insight_id ?? src.ci_build_id}`} source={src} onOpenFile={(path, line, sourceId) => handleFileSelect(path, line ?? undefined, sourceId == null ? undefined : String(sourceId))} />;
                                const filename = src.file.split('/').pop();
                                return (
                                  <span key={sIdx} className="inline-flex max-w-full items-center gap-0.5">
                                    <button
                                      type="button"
                                      id={`chat-source-link-${sIdx}`}
                                      onClick={() => handleFileSelect(src.file, src.lines?.[0] ?? undefined, src.source_id != null ? String(src.source_id) : undefined)}
                                      className={cn(
                                        "flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs transition-all shadow-inner font-medium cursor-pointer whitespace-nowrap max-w-full",
                                        theme === 'dark'
                                          ? "bg-ds-zinc-900/80 border-ds-zinc-800 hover:border-ds-zinc-700 text-ds-zinc-400 hover:text-ds-zinc-200"
                                          : "bg-ds-zinc-100/50 border-ds-zinc-200 hover:border-ds-zinc-300 text-ds-zinc-600 hover:text-ds-zinc-900"
                                      )}
                                      title={t('chatView.sourceFileTitle', { file: src.file, lines: formatLineRange(src.lines) })}
                                    >
                                      <Folder className="w-3 h-3 text-ds-indigo-400 shrink-0" />
                                      <span className="font-mono text-[0.6875rem] font-semibold truncate min-w-0">{filename}</span>
                                      <span className="text-[0.5625rem] text-ds-zinc-500 font-mono shrink-0">L{formatLineRange(src.lines)}</span>
                                    </button>
                                    {m.metadata?.chat_mode === 'evidence' && (
                                      <ProvenanceDisclosure
                                        theme={theme}
                                        variant="dialog"
                                        provenance={src.provenance ?? {
                                          kind: 'unknown',
                                          verification_status: 'unavailable',
                                          verification_note: t('provenance.historicalSourceNote'),
                                          locator: { file: src.file, lines: src.lines },
                                        }}
                                      />
                                    )}
                                  </span>
                                );
                              })}
                            </div>
                          )}

                          {m.content && (!isLoading || i !== chatMessages.length - 1) && (
                            <ChatMessageActions
                              message={m}
                              index={i}
                              theme={theme}
                              isLoading={isLoading}
                              showOriginal={originalAnswers.has(m.id ?? `index:${i}`)}
                              onToggleOriginal={() => setOriginalAnswers((current) => {
                                const next = new Set(current);
                                const key = m.id ?? `index:${i}`;
                                if (!next.delete(key)) next.add(key);
                                return next;
                              })}
                              onFeedback={handleFeedback}
                              onRetry={(index) => {
                                if (m.id != null) setVersionView(({ [m.id as number]: _shown, ...rest }) => rest);
                                handleRetryMessage(index);
                              }}
                              selectedProject={selectedProject}
                              showToast={showToast}
                              versionIndex={versionOf(m).index}
                              onVersionChange={(index) => { if (m.id != null) setVersionView(view => ({ ...view, [m.id as number]: index })); }}
                            />
                          )}
                          {i === chatMessages.length - 1 && !isLoading && (m.metadata?.suggestions?.length ?? 0) > 0 && (
                            <div className="mt-3 flex flex-wrap gap-1.5" aria-label={t('chatView.followUps')}>
                              {m.metadata?.suggestions?.map(question => (
                                <button key={question} type="button" onClick={() => handleSendChat(question)}
                                  className="rounded-full border border-ds-indigo-500/30 bg-ds-indigo-500/5 px-2.5 py-1 text-left text-[0.6875rem] text-ds-indigo-500 hover:bg-ds-indigo-500/10">
                                  {question}
                                </button>
                              ))}
                            </div>
                          )}
                        </>
                      )}
                    </div>

                    {/* User Avatar */}
                    {isUser && (
                      <div className={cn(
                        "w-7 h-7 @sm/chat:w-8 @sm/chat:h-8 rounded-full overflow-hidden shrink-0 border shadow-md transition-colors",
                        theme === 'dark' ? "border-ds-zinc-800 bg-ds-zinc-900" : "border-ds-zinc-200 bg-ds-white"
                      )}>
                        <Image
                          src="/avatars/demo-employee.png"
                          alt={t('chatView.userAvatarAlt')}
                          width={32}
                          height={32}
                          unoptimized
                          className="w-full h-full object-cover"
                        />
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

      {!followingLatest && chatMessages.length > 0 && (
        <div className="relative z-30 flex justify-center -mt-10 mb-2 pointer-events-none">
          <Button variant="outline" size="sm" onClick={scrollToLatest} aria-label={t('chatView.jumpToLatest')}
            className="pointer-events-auto h-7 rounded-full px-3 text-xs shadow-md">
            <ArrowDown className="w-3.5 h-3.5" />{t('chatView.jumpToLatest')}
          </Button>
        </div>
      )}
      <div className="sr-only" aria-live="polite">
        {isLoading ? t('chatView.srAnswering') : chatMessages[chatMessages.length - 1]?.role === 'assistant' ? t('chatView.srAnswerReady') : ''}
      </div>
      <ChatComposer
        theme={theme}
        currentMessage={currentMessage}
        setCurrentMessage={setCurrentMessage}
        handleSendChat={(attachments) => handleSendChat(undefined, undefined, attachments)}
        isLoading={isLoading}
        onStop={() => chatControls?.stop()}
        canEditLast={canEditLast}
        onEditLast={startEditLast}
        selectedProject={selectedProject}
        selectedSource={selectedSource}
        setSelectedSource={setSelectedSource}
        pinnedCode={pinnedCode}
        setPinnedCode={setPinnedCode}
        filteredSources={filteredSources}
        handleSourceFocusChange={handleSourceFocusChange}
        sessionChatMode={sessionChatMode}
        activeChatMode={activeChatMode}
        activeProfileId={activeProfileId}
        setActiveProfileId={setActiveProfileId}
        llmProfiles={llmProfiles}
        showToast={showToast}
      />
    </div>
  );
}
