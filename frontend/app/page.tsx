"use client";

import React, { useCallback, useMemo, useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Folder,
  Send,
  Menu,
  History,
  Database,
  Search,
  MoreVertical,
  Layers,
  Sparkles,
  HelpCircle,
  Clock,
  FileText,
  FileCode,
  Trash2,
  Download,
  X,
  Check,
  ExternalLink,
  Loader2,
  Activity,
  Github,
  LogOut,
  Key,
  GitBranch,
} from 'lucide-react';

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { resolveReferenceTarget } from "@/lib/referenceTarget";
import { api } from './services/api';
import { SettingsModal } from "@/components/SettingsModal";
import { SettingsProvider } from "@/components/settings/SettingsContext";
import { PanelRenderer } from "@/components/PanelRenderer";
import { WorkspaceShell } from "@/components/WorkspaceShell";
import { LoginView } from "@/components/LoginView";
import { Sidebar } from "@/components/Sidebar";
import { GlobalSearch } from "@/components/GlobalSearch";
import { PanelContentRenderer } from "@/components/PanelContentRenderer";
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { Suspense } from 'react';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { FeaturesProvider, useFeatures } from '@/lib/FeaturesContext';
import { useProjects } from '@/hooks/useProjects';
import { useKnowledgeSources } from '@/hooks/useKnowledgeSources';
import { useChatSessions } from '@/hooks/useChatSessions';
import { useChatController } from '@/hooks/useChatController';
import { usePanelNavigation } from '@/hooks/usePanelNavigation';
import { useWorkspaceLayout } from '@/hooks/useWorkspaceLayout';
import { useAiSettings } from '@/hooks/useAiSettings';
import { useDisplaySettings } from '@/hooks/useDisplaySettings';

const MemoSettingsModal = React.memo(SettingsModal);
const MemoGlobalSearch = React.memo(GlobalSearch);
const MemoSidebar = React.memo(Sidebar);



// --- Main App Component ---

function AppContent() {
  const { t } = useLanguage();
  const features = useFeatures();

  // --- Authentication States ---
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isLoginInitialized, setIsLoginInitialized] = useState(false);
  const [currentUser, setCurrentUser] = useState<any | null>(null);

  useEffect(() => {
    // Session läuft über eine httpOnly-Cookie (lokale Anmeldung, siehe backend/api/auth.py)
    api.getMe()
      .then((res) => { setIsLoggedIn(true); setCurrentUser(res.data); })
      .catch(() => setIsLoggedIn(false))
      .finally(() => setIsLoginInitialized(true));

  }, []);

  // Session abgelaufen/ungültig (401 an irgendeinem Request): der axios-Interceptor
  // in app/services/api.ts feuert dieses Event. Zurück auf die LoginView statt einer
  // still fehlschlagenden, leeren UI. isLoginInitialized bleibt true, damit direkt
  // die LoginView statt des Splash-Screens erscheint.
  useEffect(() => {
    const onUnauthorized = () => {
      setIsLoggedIn(false);
      setCurrentUser(null);
    };
    window.addEventListener('doctus:unauthorized', onUnauthorized);
    return () => window.removeEventListener('doctus:unauthorized', onUnauthorized);
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      // Auch wenn der Logout-Request scheitert: lokal ausloggen, damit der Nutzer
      // nicht in einer Sitzung festhängt, die er für beendet hält.
      setIsLoggedIn(false);
      setCurrentUser(null);
    }
  }, []);

  const [toast, setToast] = useState<any | null>(null);

  // --- Settings & Design (Workspace Split) ---
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const isEditorNavigatingRef = useRef(false);
  const aiSettings = useAiSettings({ isLoggedIn, t });
  const displaySettings = useDisplaySettings();
  const {
    activeLlmModel,
    setActiveLlmModel,
    activeEmbeddingModel,
    setActiveEmbeddingModel,
    availableModels,
    temperature,
    setTemperature,
    systemPrompt,
    setSystemPrompt,
    llmProfiles,
    setLlmProfiles,
    activeProfileId,
    setActiveProfileId,
  } = aiSettings;
  const {
    theme,
    setTheme,
    editorFontSize,
    setEditorFontSize,
    editorMinimap,
    setEditorMinimap,
    editorFontFamily,
    setEditorFontFamily,
  } = displaySettings;


  const chatEndRef = useRef(null);
  const ignoreUrlSyncRef = useRef(false);
  // handleSessionSelect is defined much further down (closes over a lot of
  // component state) but is needed by the URL-sync effect above its own
  // declaration — kept fresh via ref/effect rather than moved, same "latest
  // ref" pattern as projectsRef/selectedProjectRef below.
  const handleSessionSelectRef = useRef<(session: any) => void>(() => {});
  const showToast = useCallback((message: string, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 6000);
  }, []);

  const projectState = useProjects({ isLoggedIn, isSettingsOpen, t, showToast });
  const sourceState = useKnowledgeSources({
    isLoggedIn,
    selectedProject: projectState.selectedProject,
    t,
    showToast,
  });
  const chatState = useChatSessions({ isLoggedIn, t, showToast });
  const workspaceState = useWorkspaceLayout({
    activeSessionId: chatState.activeSessionId,
    selectedProject: projectState.selectedProject,
    selectedSource: sourceState.selectedSource,
    t,
  });

  const {
    projects, setProjects, selectedProject, setSelectedProject, files, setFiles,
    branch, setBranch, projectEntities, setProjectEntities, projectStats,
    setProjectStats, backendStatus, selectProject,
  } = projectState;
  const {
    selectedSource, setSelectedSource, selectedSourceRepoId, setSelectedSourceRepoId,
    fileReferences, setFileReferences, isLoadingReferences, isReferencesDropdownOpen,
    setIsReferencesDropdownOpen, referencesTab, setReferencesTab, activeSourceType,
    setActiveSourceType, connectedSources, setConnectedSources, pinnedSourceIds,
    setPinnedSourceIds, togglePinSource, loadFileReferences,
  } = sourceState;
  const {
    chatMessages, setChatMessages, currentMessage, setCurrentMessage, isLoading,
    setIsLoading, sessions, setSessions, isSessionsLoaded, activeSessionId,
    setActiveSessionId, handleFeedback, addAssistantHint,
  } = chatState;
  const {
    isSidebarOpen, setIsSidebarOpen, isMobile, activeMobileTab, setActiveMobileTab,
    selectedFile, setSelectedFile, selectedDoc, setSelectedDoc, selectedLine,
    setSelectedLine, activeRightTab, setActiveRightTab, fileContent, setFileContent,
    fileContentFormat, setFileContentFormat, isLoadingFile, setIsLoadingFile,
    isEditorMaximized, setIsEditorMaximized, workspaceSplit, setWorkspaceSplit,
    splitPercent, gridColumnPercent, gridRowPercent, threeColLeftPercent, threeColRightPercent, setSplitPercent, isDragging, panelConfigs, setPanelConfigs,
    layoutMode, fileNavStack, setFileNavStack, selectedEntity, setSelectedEntity,
    pinnedCode, setPinnedCode, panelFrozen, setPanelFrozen, collapsedPanels,
    setCollapsedPanels, panelFocusObject, setPanelFocusObject, panelSelections,
    setPanelSelections, panelHistory, setPanelHistory, splitContainerRef,
    activePanelIndex, setActivePanelIndex, isRestoringSnapshotRef, isPanelHistoryNavRef, togglePanelFreeze,
    togglePanelCollapse, closePanel, addPanel, ensurePanelType, isPanelCollapsed,
    cellCls, handlePanelEntitySelect: updatePanelEntitySelection, goBackPanel, goForwardPanel,
    handleDividerMouseDown, handleGridResizePointerDown, handleThreeColLeftDividerPointerDown,
    handleThreeColRightDividerPointerDown, restoreWorkspaceSnapshot,
  } = workspaceState;

  const router = useRouter();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const chatUuidParam = searchParams.get('chat');

  // Source state and loading live in useKnowledgeSources.

  const editorRef = useRef<any>(null);

  // Mobile-tab synchronization lives in useWorkspaceLayout.

  // Initial connection check and repository loading
  useEffect(() => {
    // Monaco's harmless "Canceled" error is already suppressed globally by the
    // capture-phase <script> in app/layout.tsx, which runs in <head> before
    // this component ever mounts — a second copy of the same listeners here
    // was dead weight (layout's stopImmediatePropagation() fires first).
    (() => {

    })();
  }, []);

  // Handle chat UUID from URL
  useEffect(() => {
    if (!isSessionsLoaded) return;

    if (ignoreUrlSyncRef.current) {
      const activeSession = sessions.find(s => s.id === activeSessionId);
      if (!chatUuidParam || (activeSession && chatUuidParam === activeSession.uuid)) {
        ignoreUrlSyncRef.current = false;
      }
      return;
    }

    if (chatUuidParam) {
      const session = sessions.find(s => s.uuid === chatUuidParam);
      if (session) {
        if (session.id !== activeSessionId) {
          handleSessionSelectRef.current(session);
        }
      } else {
        // Fetch shared session by UUID from backend (for other users accessing the shared link)
        api.getChatSessionByUuid(chatUuidParam)
          .then(res => {
            const fetchedSession = res.data;
            if (fetchedSession) {
              setSessions(prev => {
                if (!prev.some(s => s.id === fetchedSession.id)) {
                  return [fetchedSession, ...prev];
                }
                return prev;
              });
              handleSessionSelectRef.current(fetchedSession);
            }
          })
          .catch(err => {
            console.error("Shared session fetch failed:", err);
            // Clear invalid chat UUID from URL
            const params = new URLSearchParams(window.location.search);
            params.delete('chat');
            router.push(`${pathname}?${params.toString()}`);
            showToast(t('page.toast.sharedChatNotFound'), "error");
          });
      }
    }
  }, [chatUuidParam, sessions, activeSessionId, isSessionsLoaded, pathname, router, t, setSessions, showToast]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  // Resets just the chat/session identity — used internally whenever the app
  // auto-starts a fresh conversation as a side effect of something else (switching
  // project/file mid-chat, removing the active session, opening the graph view),
  // where the caller deliberately keeps its own view/panel state around afterward.
  const resetChatSession = useCallback(() => {
    ignoreUrlSyncRef.current = true;
    setChatMessages([]);
    setSelectedFile(null);
    setIsEditorMaximized(false);
    setActiveSessionId(null);

    // Clear URL chat parameter
    router.push(pathname);

    showToast(t('page.toast.newChatStarted'), "success");
  }, [pathname, router, showToast, t, setActiveSessionId, setChatMessages, setIsEditorMaximized, setSelectedFile]);

  // "+ Neuer Chat": resets the conversation/views to a clean slate, but
  // deliberately keeps the current project focus (selectedProject/files/
  // projectEntities) — the button starts a fresh chat *within* the current
  // project, it does not back out to "no project selected". Every other
  // open view/panel, file focus, and modal closes, not just the message
  // list (they otherwise stay open and keep adapting to whatever file was
  // previously focused).
  const startNewChat = useCallback(() => {
    resetChatSession();
    setSelectedSource(null);
    setSelectedDoc(null);
    setSelectedEntity(null);
    setSelectedLine(null);
    setActiveRightTab('code');
    setFileContent("");
    setFileContentFormat("text");
    setCurrentMessage("");
    setPinnedCode(null);
    setFileNavStack([]);
    setPanelConfigs(['chat']);
    setPanelSelections([{ selectedFile: null, selectedDoc: null, selectedEntity: null, selectedLine: null }]);
    setPanelHistory([{ past: [], future: [] }]);
    setPanelFrozen([false]);
    setCollapsedPanels([false]);
    setPanelFocusObject([null]);
    setSplitPercent(45);
    setWorkspaceSplit("45/55");
    setIsSettingsOpen(false);
  }, [resetChatSession, setActiveRightTab, setCollapsedPanels, setCurrentMessage, setFileContent, setFileContentFormat, setFileNavStack, setIsSettingsOpen, setPanelConfigs, setPanelFocusObject, setPanelFrozen, setPanelHistory, setPanelSelections, setPinnedCode, setSelectedDoc, setSelectedEntity, setSelectedLine, setSelectedSource, setSplitPercent, setWorkspaceSplit]);

  const handleProjectSelect = useCallback(async (project) => {
    if (!project) {
      const activeSession = sessions.find(s => s.id === activeSessionId);
      if (activeSessionId && activeSession && activeSession.project_id !== null) {
        resetChatSession();
      }
      await selectProject(null);
      showToast(t('page.toast.projectSelectedGeneral') || "Allgemeiner Kontext ausgewählt", "success");
      return;
    }
    // status/url are only populated when a git repo is attached (see serialize_project) —
    // a git-free project has status=null and must stay selectable.
    if (project.url && project.status !== 'completed') {
      showToast(t('page.toast.projectStillAnalyzing', { name: project.name }), 'warning');
      return;
    }
    const activeSession = sessions.find(s => s.id === activeSessionId);
    if (activeSessionId && activeSession && activeSession.project_id !== project.id) {
      resetChatSession();
    }

    await selectProject(project);
  }, [activeSessionId, resetChatSession, selectProject, sessions, showToast, t]);

  const {
    handleShareChat,
    handleSendChat,
    handleRetryMessage,
    handleSessionSelect,
    handleRemoveSession,
  } = useChatController({
    t,
    showToast,
    ignoreUrlSyncRef,
    activeSessionId,
    setActiveSessionId,
    chatMessages,
    setChatMessages,
    currentMessage,
    setCurrentMessage,
    isLoading,
    setIsLoading,
    setSessions,
    selectedProject,
    selectedSource,
    setSelectedSource,
    pinnedCode,
    branch,
    temperature,
    systemPrompt,
    activeProfileId,
    llmProfiles,
    projects,
    connectedSources,
    handleProjectSelect,
    restoreWorkspaceSnapshot,
    resetChatSession,
  });

  useEffect(() => {
    handleSessionSelectRef.current = handleSessionSelect;
  }, [handleSessionSelect]);

  // File-reference loading lives in useKnowledgeSources.

  const handleFileSelect = useCallback(async (path, line = null, sourceId = null, projectOverride = null) => {
    // Chunks einer Datei liegen unter "<pfad>#<suffix>" — für die Dateiauswahl
    // zählt nur der Pfad davor.
    const cleanPath = path && path.includes('#') ? path.split('#')[0] : path;

    const project = projectOverride || selectedProject;
    if (!isEditorNavigatingRef.current) {
      setFileNavStack([]);
      setIsEditorMaximized(false);
    }
    isEditorNavigatingRef.current = false;
    setActiveMobileTab('editor');
    setIsReferencesDropdownOpen(false); // Close dropdown when opening a new file
    if (!line) {
      setSelectedEntity(null);
    }

    // Ensure we are in a session compatible with the selected project.
    // If the active session belongs to a different project than our current focus, start a new chat.
    const activeSession = sessions.find(s => s.id === activeSessionId);
    if (activeSessionId && activeSession && project && activeSession.project_id !== project.id) {
      resetChatSession();
    }

    const { isDoc, isWebOrigin, resolvedSourceId } = resolveReferenceTarget(cleanPath, sourceId, connectedSources);

    if (resolvedSourceId && (isWebOrigin || isDoc)) {
      if (isWebOrigin) {
        setSelectedDoc({ id: resolvedSourceId, name: cleanPath, isWebOrigin: true, url: cleanPath });
        setSelectedFile(null);
        setSelectedLine(null);
        setActiveRightTab('weborigin');
        ensurePanelType('webview');
      } else {
        setSelectedDoc({ id: resolvedSourceId, name: cleanPath });
        setSelectedFile(null);
        setSelectedLine(null);
        setActiveRightTab('doc');
        ensurePanelType('doc');
      }
    } else {
      setSelectedFile(cleanPath);
      setSelectedDoc(resolvedSourceId ? { id: resolvedSourceId, name: cleanPath } : null);
      setSelectedLine(line);
      setActiveRightTab('code');
      ensurePanelType('code');
    }
    try {
      setIsLoadingFile(true);
      setFileContent("");
      let content = "";
      if (resolvedSourceId) {
        if (isWebOrigin) {
          const res = await api.resolveWebOrigin(resolvedSourceId, cleanPath, theme);
          content = res.data.content;
          setFileContentFormat("html");
          if (res.data.url) {
            setSelectedDoc(prev => prev ? { ...prev, url: res.data.url } : null);
          }
          showToast(t('page.toast.webpageLoaded', { name: cleanPath.split('/').pop() || t('page.fallbackContent') }), "success");
        } else {
          const res = await api.getKnowledgeSourceContent(resolvedSourceId, cleanPath);
          content = res.data.content;
          setFileContentFormat(res.data.format || (cleanPath.endsWith(".md") ? "markdown" : "text"));
          showToast(t('page.toast.documentLoaded', { name: cleanPath.split('/').pop() }), "success");
        }
      } else {
        // project.repo_id ist die KnowledgeSource-id der Git-Quelle (siehe
        // serialize_project in backend/api/serializers.py) -- es gibt keinen
        // eigenen "/repositories/.../file-content"-Endpunkt, der Git-Worktree
        // wird über den Knowledge-Source-Content-Endpunkt gelesen (siehe
        // get_knowledge_source_content in backend/api/knowledge_sources.py).
        const res = await api.getKnowledgeSourceContent(project.repo_id, cleanPath);
        content = res.data.content;
        setFileContentFormat(res.data.format || (cleanPath.endsWith(".md") ? "markdown" : "text"));
        showToast(t('page.toast.fileLoaded', { name: cleanPath.split('/').pop() }), "success");
      }
      setFileContent(content);

      // Load references
      if (!line || resolvedSourceId) {
        loadFileReferences(path, null, projectOverride);
      }

      if (line) {
        setTimeout(() => {
          if (editorRef.current) {
            editorRef.current.revealLineInCenter(line);
            editorRef.current.setPosition({ lineNumber: line, column: 1 });
            if (editorRef.current.deltaDecorations) {
              const range = {
                startLineNumber: line,
                startColumn: 1,
                endLineNumber: line,
                endColumn: 100
              };
              let decs = editorRef.current.deltaDecorations([], [
                {
                  range: range,
                  options: {
                    isWholeLine: true,
                    className: 'bg-ds-indigo-500/20 border-y border-ds-indigo-500/30'
                  }
                }
              ]);
              setTimeout(() => {
                if (editorRef.current) {
                  editorRef.current.deltaDecorations(decs, []);
                }
              }, 4000);
            }
          }
        }, 150);
      }
    } catch (err) {
      showToast(t('page.toast.fileLoadFailed'), "error");
    } finally {
      setIsLoadingFile(false);
    }
  }, [activeSessionId, connectedSources, ensurePanelType, loadFileReferences, resetChatSession, selectedProject, sessions, setActiveMobileTab, setActiveRightTab, setFileContent, setFileContentFormat, setFileNavStack, setIsEditorMaximized, setIsLoadingFile, setIsReferencesDropdownOpen, setSelectedDoc, setSelectedEntity, setSelectedFile, setSelectedLine, showToast, theme, t]);

  const {
    pinFileFocus,
    pinEntityFocus,
    handlePanelEntitySelect,
    handlePanelFileSelect,
    handleDocFocusRequest,
    handleGutterClick,
    handleGutterAskEntity,
    handleEntitySelect,
    handleNavigateBack,
  } = usePanelNavigation({
    t,
    selectedProject,
    selectedSource,
    connectedSources,
    projectEntities,
    panelConfigs,
    panelFrozen,
    panelSelections,
    fileNavStack,
    setPinnedCode,
    setPanelFocusObject,
    setPanelSelections,
    setPanelHistory,
    setActiveMobileTab,
    setSelectedDoc,
    setSelectedFile,
    setSelectedEntity,
    setSelectedLine,
    setFileNavStack,
    setIsEditorMaximized,
    isPanelHistoryNavRef,
    isEditorNavigatingRef,
    addPanel,
    ensurePanelType,
    updatePanelEntitySelection,
    handleFileSelect,
    loadFileReferences,
  });

  const handleSearchResultSelect = useCallback(async (result: any) => {
    const meta = result.node_meta || {};
    const targetProjectId = result.node_type === 'project' ? result.node_id : meta.project_id;

    let targetProject = selectedProject;
    if (targetProjectId && targetProjectId !== selectedProject?.id) {
      const found = projects.find((p: any) => p.id === targetProjectId);
      if (found) {
        await handleProjectSelect(found);
        targetProject = found;
      }
    }

    if (result.node_type === 'entity') {
      await handleEntitySelect({
        id: result.node_id,
        file_path: meta.file_path,
        start_line: meta.start_line,
        name: result.node_label,
        type: meta.type,
        source_id: meta.source_id,
      }, targetProject);
    } else if (result.node_type === 'document') {
      const filePath = meta.file_path || result.node_label;
      pinFileFocus(filePath, null, meta.source_id ?? null);
      await handleFileSelect(filePath, null, meta.source_id, targetProject);
    } else if (result.node_type === 'knowledge_source') {
      setSelectedSource({ id: result.node_id, name: result.node_label, project_id: meta.project_id, type: meta.type });
      showToast(t('page.toast.sourceFocused', { name: result.node_label }), "success");
    }
  }, [handleEntitySelect, handleFileSelect, handleProjectSelect, pinFileFocus, projects, selectedProject, setSelectedSource, showToast, t]);

  const handleOpenGraphView = useCallback(() => {
    resetChatSession();
    setActiveRightTab('graph');
    setActiveMobileTab('graph');

    const existingIndex = panelConfigs.indexOf('graph');
    if (existingIndex === -1) {
      ensurePanelType('graph', { selectedFile: null, selectedDoc: null, selectedEntity: null }, true);
    } else {
      setPanelSelections(prev => {
        const next = [...prev];
        next[existingIndex] = { selectedFile: null, selectedDoc: null, selectedEntity: null, selectedLine: null };
        return next;
      });
      setPanelFrozen(prev => {
        const next = [...prev];
        next[existingIndex] = true;
        return next;
      });
    }
  }, [ensurePanelType, panelConfigs, resetChatSession, setActiveMobileTab, setActiveRightTab, setPanelFrozen, setPanelSelections]);

  const handleCloseSettings = useCallback(() => setIsSettingsOpen(false), []);
  const handleSidebarFileSelect = useCallback((path: string, line?: number, sourceId?: string) => {
    pinFileFocus(path, line ?? null, sourceId ?? null);
    return handleFileSelect(path, line, sourceId);
  }, [handleFileSelect, pinFileFocus]);

  // Keep the context identity stable while unrelated workspace/chat state
  // changes. Settings tabs subscribe to this value, so an inline object here
  // would otherwise rerender the complete settings tree on every keystroke or
  // streamed chat chunk.
  const settingsContextValue = useMemo(() => ({
    theme,
    setTheme,
    projects,
    setProjects,
    selectedProject,
    setSelectedProject,
    setFiles,
    showToast,
    backendStatus,
    activeLlmModel,
    setActiveLlmModel,
    activeEmbeddingModel,
    setActiveEmbeddingModel,
    availableModels,
    temperature,
    setTemperature,
    systemPrompt,
    setSystemPrompt,
    llmProfiles,
    setLlmProfiles,
    activeProfileId,
    setActiveProfileId,
    editorFontSize,
    setEditorFontSize,
    editorMinimap,
    setEditorMinimap,
    editorFontFamily,
    setEditorFontFamily,
    workspaceSplit,
    setWorkspaceSplit,
    connectedSources,
    setConnectedSources,
    projectStats,
    pinnedSourceIds,
    togglePinSource,
    currentUser,
  }), [
    activeEmbeddingModel,
    activeLlmModel,
    activeProfileId,
    availableModels,
    backendStatus,
    connectedSources,
    currentUser,
    editorFontFamily,
    editorFontSize,
    editorMinimap,
    llmProfiles,
    pinnedSourceIds,
    projectStats,
    projects,
    selectedProject,
    showToast,
    systemPrompt,
    temperature,
    theme,
    togglePinSource,
    workspaceSplit,
    setConnectedSources,
    setFiles,
    setProjects,
    setSelectedProject,
    setActiveEmbeddingModel,
    setActiveLlmModel,
    setActiveProfileId,
    setEditorFontFamily,
    setEditorFontSize,
    setEditorMinimap,
    setLlmProfiles,
    setSystemPrompt,
    setTemperature,
    setTheme,
    setWorkspaceSplit,
  ]);

  // Divider interaction lives in useWorkspaceLayout.

  const renderPanelContent = (index: number, contentType: string, selection: any) => (
    <PanelContentRenderer
      index={index}
      contentType={contentType}
      selection={selection}
      theme={theme}
      isSidebarOpen={isSidebarOpen}
      selectedProject={selectedProject}
      handleProjectSelect={handleProjectSelect}
      pinnedCode={pinnedCode}
      setPinnedCode={setPinnedCode}
      chatMessages={chatMessages}
      currentMessage={currentMessage}
      setCurrentMessage={setCurrentMessage}
      isLoading={isLoading}
      handleSendChat={handleSendChat}
      handleRetryMessage={handleRetryMessage}
      handleFeedback={handleFeedback}
      addAssistantHint={addAssistantHint}
      handlePanelFileSelect={handlePanelFileSelect}
      activeProfileId={activeProfileId}
      setActiveProfileId={setActiveProfileId}
      llmProfiles={llmProfiles}
      showToast={showToast}
      selectedSource={selectedSource}
      setSelectedSource={setSelectedSource}
      connectedSources={connectedSources}
      activeLlmModel={activeLlmModel}
      activeEmbeddingModel={activeEmbeddingModel}
      editorFontSize={editorFontSize}
      editorFontFamily={editorFontFamily}
      editorMinimap={editorMinimap}
      isReferencesDropdownOpen={isReferencesDropdownOpen}
      setIsReferencesDropdownOpen={setIsReferencesDropdownOpen}
      referencesTab={referencesTab}
      setReferencesTab={setReferencesTab}
      handlePanelEntitySelect={handlePanelEntitySelect}
      handleGutterClick={handleGutterClick}
      handleGutterAskEntity={handleGutterAskEntity}
      projectEntities={projectEntities}
      fileNavStack={fileNavStack}
      handleNavigateBack={handleNavigateBack}
      handleDocFocusRequest={handleDocFocusRequest}
      layoutMode={layoutMode}
      chatEndRef={chatEndRef}
      currentUser={currentUser}
    />
  );

  const handlePanelContentTypeChange = (index: number, newType: string) => {
    setPanelConfigs((previous) => {
      const next = [...previous];
      next[index] = newType;
      return next;
    });
    setPanelFocusObject((previous) => {
      const next = [...previous];
      next[index] = null;
      return next;
    });
    setPanelHistory((previous) => {
      const next = [...previous];
      next[index] = { past: [], future: [] };
      return next;
    });
  };

  const renderPanel = (index: number) => {
    const contentType = panelConfigs[index] || 'chat';
    const selection = panelSelections[index] || { selectedFile: null, selectedDoc: null, selectedEntity: null, selectedLine: null };
    return (
      <PanelRenderer
        index={index}
        contentType={contentType}
        selection={selection}
        focusObject={panelFocusObject[index]}
        theme={theme}
        t={t}
        selectedProject={selectedProject}
        panelFrozen={Boolean(panelFrozen[index])}
        collapsed={Boolean(collapsedPanels[index])}
        panelCount={panelConfigs.length}
        panelHistory={panelHistory[index]}
        linkManagerEnabled={features.views.linkManager}
        onContentTypeChange={handlePanelContentTypeChange}
        onExpand={togglePanelCollapse}
        onMouseEnter={setActivePanelIndex}
        onHistoryBack={goBackPanel}
        onHistoryForward={goForwardPanel}
        onToggleFreeze={togglePanelFreeze}
        onCollapse={togglePanelCollapse}
        onClose={closePanel}
        content={renderPanelContent(index, contentType, selection)}
      />
    );
  };

  if (!isLoginInitialized) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-ds-zinc-950 text-ds-zinc-500 text-xs gap-2">
        <Loader2 className="w-4 h-4 animate-spin text-ds-indigo-500" />
        {t('page.loading')}
      </div>
    );
  }

  if (!isLoggedIn) {
    return (
      <LoginView
        onAuthenticated={() => {
          api.getMe()
            .then((res) => { setIsLoggedIn(true); setCurrentUser(res.data); })
            .catch(() => setIsLoggedIn(false));
        }}
      />
    );
  }

  return (
    <div className={cn(
      "h-screen w-screen flex flex-col overflow-hidden font-sans relative transition-colors duration-150 doctus-canvas",
      theme === 'dark' ? "bg-ds-zinc-950 text-ds-zinc-100" : "bg-ds-zinc-50 text-ds-zinc-900"
    )}>

      <div className="absolute left-0 top-0 bottom-0 w-1 doctus-brand-gradient pointer-events-none z-50" />

      {/* Custom Toast Notifications */}
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            className={cn(
              "fixed bottom-4 right-4 z-[100] flex items-center gap-2.5 px-4 py-3 rounded-lg border shadow-2xl backdrop-blur-md text-xs font-semibold tracking-wide transition-colors duration-200",
              toast.type === 'success'
                ? (theme === 'dark' ? "bg-ds-emerald-950/90 border-ds-emerald-800/40 text-ds-emerald-300" : "bg-ds-emerald-50/95 border-ds-emerald-200 text-ds-emerald-800")
                : (theme === 'dark' ? "bg-ds-red-950/90 border-ds-red-800/40 text-ds-red-300" : "bg-ds-red-50/95 border-ds-red-200 text-ds-red-800")
            )}
          >
            {toast.type === 'success' ? <Check className="w-4 h-4 text-ds-emerald-500" /> : <X className="w-4 h-4 text-ds-red-500" />}
            <span>{toast.message}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Advanced Settings Modal Dialog */}
      <SettingsProvider
        value={settingsContextValue}
      >
        <MemoSettingsModal
          isOpen={isSettingsOpen}
          onClose={handleCloseSettings}
        />
      </SettingsProvider>

      {/* Header bar: search (feature-gated), sidebar toggle, and the app-level
          actions (graph, theme, settings) — always mounted so those actions
          stay reachable even if the search feature is disabled. Link Manager
          is no longer a dedicated header action — it's opened like any other
          panel type via the "+" add-view menu or a panel's type selector. */}
      <MemoGlobalSearch
        theme={theme}
        setTheme={setTheme}
        projects={projects}
        connectedSources={connectedSources}
        onSelectResult={handleSearchResultSelect}
        isSidebarOpen={isSidebarOpen}
        setIsSidebarOpen={setIsSidebarOpen}
        setIsSettingsOpen={setIsSettingsOpen}
        onOpenGraphView={handleOpenGraphView}
        panelConfigs={panelConfigs}
        onAddPanel={addPanel}
        selectedProject={selectedProject}
        onProjectSelect={handleProjectSelect}
        onShareChat={handleShareChat}
        currentUser={currentUser}
      />

      <div className="flex-1 flex overflow-hidden min-h-0">

      {/* LEFT SIDEBAR PANEL MOBILE OVERLAY */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-ds-black/60 z-40 md:hidden animate-in fade-in duration-200"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* LEFT SIDEBAR PANEL */}
      <MemoSidebar
        theme={theme}
        isSidebarOpen={isSidebarOpen}
        setIsSidebarOpen={setIsSidebarOpen}
        backendStatus={backendStatus}
        startNewChat={startNewChat}
        sessions={sessions}
        activeSessionId={activeSessionId}
        handleSessionSelect={handleSessionSelect}
        handleRemoveSession={handleRemoveSession}
        selectedProject={selectedProject}
        selectedFile={selectedFile}
        selectedDoc={selectedDoc}
        handleFileSelect={handleSidebarFileSelect}
        handleLogout={handleLogout}
        connectedSources={connectedSources}
        pinnedSourceIds={pinnedSourceIds}
        currentUser={currentUser}
      />

      {/* MAIN CONTENT AREA */}
      <main className="flex-1 flex flex-col relative min-w-0 z-10">

        {/* Project identity is a precise edge marker, not an ambient glow. */}
        {selectedProject?.color && (
          <div
            className="absolute left-0 right-0 top-0 h-[2px] pointer-events-none z-20 transition-colors duration-300"
            style={{
              background: `radial-gradient(circle at 50% 50%, ${selectedProject.color} 0%, transparent 65%)`
            }}
          />
        )}

        <WorkspaceShell
          theme={theme}
          t={t}
          isMobile={isMobile}
          selectedFile={selectedFile}
          selectedDoc={selectedDoc}
          activeRightTab={activeRightTab}
          setActiveRightTab={setActiveRightTab}
          activeMobileTab={activeMobileTab}
          setActiveMobileTab={setActiveMobileTab}
          panelConfigs={panelConfigs}
          layoutMode={layoutMode}
          splitPercent={splitPercent}
          gridColumnPercent={gridColumnPercent}
          gridRowPercent={gridRowPercent}
          threeColLeftPercent={threeColLeftPercent}
          threeColRightPercent={threeColRightPercent}
          isDragging={isDragging}
          splitContainerRef={splitContainerRef}
          handleDividerMouseDown={handleDividerMouseDown}
          handleGridResizePointerDown={handleGridResizePointerDown}
          handleThreeColLeftDividerPointerDown={handleThreeColLeftDividerPointerDown}
          handleThreeColRightDividerPointerDown={handleThreeColRightDividerPointerDown}
          isPanelCollapsed={isPanelCollapsed}
          cellCls={cellCls}
          renderPanel={renderPanel}
        />
      </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <FeaturesProvider>
      <Suspense fallback={null}>
        <AppContent />
      </Suspense>
    </FeaturesProvider>
  );
}
