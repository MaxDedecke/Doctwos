"use client";
import type { LlmProfile } from '@/hooks/useAiSettings';
import type { ChatPinnedFocus } from '@/lib/chatFocus';
import type { ChatMessage, ChatMetadata, CodeEntity, KnowledgeSource, Project, User, WorkspaceDocument } from '@/types/domain';

import { CallGraphView } from '@/components/CallGraphView';
import { ChatView } from '@/components/ChatView';
import { LinkManagerView } from '@/components/LinkManagerView';
import { SplitPaneWorkspace } from '@/components/SplitPaneWorkspace';
import type { PanelSelection } from '@/lib/panelHistory';
import React from 'react';

type PanelTab = 'code' | 'doc' | 'weborigin' | 'graph';

type PanelContentRendererProps = {
  index: number;
  contentType: string;
  selection: PanelSelection;
  theme: string;
  isSidebarOpen: boolean;
  selectedProject: Project | null;
  handleProjectSelect: (project: Project | null) => void | Promise<void>;
  pinnedCode: ChatPinnedFocus | null;
  setPinnedCode: (code: ChatPinnedFocus | null) => void;
  chatMessages: ChatMessage[];
  currentMessage: string;
  setCurrentMessage: (message: string) => void;
  isLoading: boolean;
  handleSendChat: (overrideMessage?: string, extraMetadata?: ChatMetadata) => void;
  handleRetryMessage: (index: number) => void;
  handleFeedback: (messageId: number, feedback: 'up' | 'down') => void;
  addAssistantHint: (text: string) => void;
  handlePanelFileSelect: (
    index: number,
    path: string | null,
    line?: number | null,
    sourceId?: number | string | null,
    openIfMissing?: boolean,
  ) => Promise<void>;
  activeProfileId: string;
  setActiveProfileId: (value: string) => void;
  llmProfiles: LlmProfile[];
  showToast: (message: string, type?: string) => void;
  selectedSource: KnowledgeSource | null;
  setSelectedSource: (source: KnowledgeSource | null) => void;
  connectedSources: KnowledgeSource[];
  activeLlmModel: string;
  activeEmbeddingModel: string;
  editorFontSize: number;
  editorFontFamily: string;
  editorMinimap: boolean;
  isReferencesDropdownOpen: boolean;
  setIsReferencesDropdownOpen: (open: boolean) => void;
  referencesTab: 'code' | 'docs';
  setReferencesTab: (tab: 'code' | 'docs') => void;
  handlePanelEntitySelect: (index: number, entity: CodeEntity) => Promise<void> | void;
  handleGutterClick: (index: number, lineNumber: number, lineContent: string) => void;
  handleGutterAskEntity: (index: number, entity: CodeEntity) => void;
  projectEntities: CodeEntity[];
  fileNavStack: Array<{ file: string | null; doc: WorkspaceDocument | null; tab: PanelTab }>;
  handleNavigateBack: () => Promise<void> | void;
  handleDocFocusRequest: (filePath: string, sourceId: number | string | null) => void;
  layoutMode?: '1-pane' | 'split' | '3-col' | '4-grid';
  chatEndRef: React.RefObject<HTMLDivElement>;
  currentUser: User | null;
};

/**
 * Owns the view-specific content inside a workspace panel. The page keeps
 * panel state and cross-panel navigation; this component only maps that
 * shared state to the selected view.
 */
export function PanelContentRenderer({
  index,
  contentType,
  selection,
  theme,
  isSidebarOpen,
  selectedProject,
  handleProjectSelect,
  pinnedCode,
  setPinnedCode,
  chatMessages,
  currentMessage,
  setCurrentMessage,
  isLoading,
  handleSendChat,
  handleRetryMessage,
  handleFeedback,
  addAssistantHint,
  handlePanelFileSelect,
  activeProfileId,
  setActiveProfileId,
  llmProfiles,
  showToast,
  selectedSource,
  setSelectedSource,
  connectedSources,
  activeLlmModel,
  activeEmbeddingModel,
  editorFontSize,
  editorFontFamily,
  editorMinimap,
  isReferencesDropdownOpen,
  setIsReferencesDropdownOpen,
  referencesTab,
  setReferencesTab,
  handlePanelEntitySelect,
  handleGutterClick,
  handleGutterAskEntity,
  projectEntities,
  fileNavStack,
  handleNavigateBack,
  handleDocFocusRequest,
  layoutMode,
  chatEndRef,
  currentUser,
}: PanelContentRendererProps) {
  if (contentType === 'chat') {
    return (
      <ChatView
        theme={theme}
        isSidebarOpen={isSidebarOpen}
        selectedProject={selectedProject}
        onProjectSelect={handleProjectSelect}
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
        handleFileSelect={(path, line, sourceId) => handlePanelFileSelect(index, path, line, sourceId)}
        activeProfileId={activeProfileId}
        setActiveProfileId={setActiveProfileId}
        llmProfiles={llmProfiles}
        showToast={showToast}
        selectedFile={selection.selectedFile}
        selectedDoc={selection.selectedDoc}
        splitClasses={{ chat: 'w-full', editor: 'w-full' }}
        chatEndRef={chatEndRef}
        selectedSource={selectedSource}
        setSelectedSource={setSelectedSource}
        connectedSources={connectedSources}
      />
    );
  }

  if (contentType === 'callgraph') {
    return (
      <CallGraphView
        theme={theme}
        focusedEntity={selection.selectedEntity}
        projectId={selectedProject?.id}
        onFileSelect={(path, line, sourceId) => handlePanelFileSelect(index, path, line, sourceId, true)}
      />
    );
  }

  if (contentType === 'linkmanager') {
    return (
      <LinkManagerView
        selectedProject={selectedProject}
        theme={theme}
        currentUser={currentUser}
        llmProfiles={llmProfiles}
        activeProfileId={activeProfileId}
        setActiveProfileId={setActiveProfileId}
        showToast={showToast}
      />
    );
  }

  const activeRightTab = contentType === 'doc'
    ? 'doc'
    : contentType === 'graph'
      ? 'graph'
      : contentType === 'webview'
        ? 'weborigin'
        : 'code';

  return (
    <SplitPaneWorkspace
      theme={theme}
      selectedFile={selection.selectedFile}
      selectedDoc={selection.selectedDoc}
      selectedLine={selection.selectedLine}
      activeRightTab={activeRightTab}
      setActiveRightTab={() => {}}
      isEditorMaximized={false}
      setIsEditorMaximized={() => {}}
      setSelectedFile={(path) => handlePanelFileSelect(index, path)}
      setSelectedDoc={(doc) => handlePanelFileSelect(index, doc?.name || null, null, doc?.id || null)}
      handleFileSelect={(path, line, sourceId, openIfMissing) =>
        handlePanelFileSelect(index, path, line, sourceId, openIfMissing)
      }
      isReferencesDropdownOpen={isReferencesDropdownOpen}
      setIsReferencesDropdownOpen={setIsReferencesDropdownOpen}
      referencesTab={referencesTab}
      setReferencesTab={setReferencesTab}
      selectedEntity={selection.selectedEntity}
      splitClasses={{ chat: 'w-full', editor: 'w-full' }}
      activeLlmModel={activeLlmModel}
      activeEmbeddingModel={activeEmbeddingModel}
      editorFontSize={editorFontSize}
      editorFontFamily={editorFontFamily}
      editorMinimap={editorMinimap}
      selectedProject={selectedProject}
      projectEntities={projectEntities}
      handleEntitySelect={(entity) => handlePanelEntitySelect(index, entity)}
      onGutterClick={(lineNumber, lineContent) => handleGutterClick(index, lineNumber, lineContent)}
      onGutterAskEntity={(entity) => handleGutterAskEntity(index, entity)}
      fileNavStack={fileNavStack}
      onNavigateBack={handleNavigateBack}
      onDocFocus={contentType === 'webview' ? undefined : handleDocFocusRequest}
      layoutMode={contentType === 'graph' ? layoutMode : undefined}
    />
  );
}
