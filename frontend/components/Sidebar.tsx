"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus,
  MessageSquare,
  Trash2,
  ChevronDown,
  ChevronRight,
  Folder,
  Search,
  X,
  Loader2,
  LogOut,
  Database,
  FileText,
  Pin
} from 'lucide-react';
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useFeatures } from '@/lib/FeaturesContext';
import { api } from '@/app/services/api';
import { DoctusLogo } from './Logo';

interface SidebarProps {
  theme: string;
  isSidebarOpen: boolean;
  setIsSidebarOpen: (val: boolean) => void;
  backendStatus: string;
  startNewChat: () => void;
  sessions: any[];
  activeSessionId: number | null;
  handleSessionSelect: (session: any) => void;
  handleRemoveSession: (id: number, e: React.MouseEvent) => void;
  selectedProject: any;
  selectedFile: string | null;
  selectedDoc: any | null;
  handleFileSelect: (path: string, line?: number, sourceId?: string) => void;
  handleLogout: () => void;
  connectedSources: any[];
  pinnedSourceIds: number[];
}

export function Sidebar({
  theme,
  isSidebarOpen,
  setIsSidebarOpen,
  backendStatus,
  startNewChat,
  sessions,
  activeSessionId,
  handleSessionSelect,
  handleRemoveSession,
  selectedProject,
  selectedFile,
  selectedDoc,
  handleFileSelect,
  handleLogout,
  connectedSources = [],
  pinnedSourceIds = []
}: SidebarProps) {
  const { t } = useLanguage();
  const features = useFeatures();
  const [sidebarWidth, setSidebarWidth] = useState(280);
  const [isResizingSidebar, setIsResizingSidebar] = useState(false);
  const [isHistoryExpanded, setIsHistoryExpanded] = useState(true);
  const [isFilesExpanded, setIsFilesExpanded] = useState(true);
  const [collapsedFolders, setCollapsedFolders] = useState<Record<string, boolean>>({});
  const [expandedFolderId, setExpandedFolderId] = useState<number | null>(null);
  const [sourceFiles, setSourceFiles] = useState<Record<number, string[]>>({});
  const [loadingSourceId, setLoadingSourceId] = useState<number | null>(null);

  const loadSourceFiles = async (sourceId: number) => {
    setLoadingSourceId(sourceId);
    try {
      const res = await api.getKnowledgeSourceFiles(sourceId);
      setSourceFiles(prev => ({ ...prev, [sourceId]: res.data.files || [] }));
    } catch (e) {
      console.error("Failed to load source files", e);
    } finally {
      setLoadingSourceId(null);
    }
  };

  const renderSourceTreeNode = (node: any, sourceId: number, depth = 0): React.ReactNode => {
    const isFolder = node.type === 'folder';
    const isCollapsed = !!collapsedFolders[node.path];

    if (isFolder) {
      const childrenKeys = Object.keys(node.children).sort((a, b) => {
        const typeA = node.children[a].type;
        const typeB = node.children[b].type;
        if (typeA === typeB) return a.localeCompare(b);
        return typeA === 'folder' ? -1 : 1;
      });

      return (
        <div key={node.path} className="space-y-0.5">
          <button
            type="button"
            onClick={() => toggleFolder(node.path)}
            className={cn(
              "w-full flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-semibold transition-all text-left",
              theme === 'dark' ? "text-ds-zinc-400 hover:bg-ds-zinc-800/40 hover:text-ds-zinc-200" : "text-ds-zinc-650 hover:bg-ds-zinc-200/55 hover:text-ds-zinc-850"
            )}
            style={{ paddingLeft: `${Math.max(8, depth * 12)}px` }}
          >
            <span className="w-3.5 h-3.5 flex items-center justify-center shrink-0">
              {isCollapsed ? (
                <ChevronRight className="w-3.5 h-3.5 text-ds-zinc-500" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 text-ds-zinc-500" />
              )}
            </span>
            <Folder className="w-3.5 h-3.5 shrink-0 opacity-70 text-ds-indigo-500" />
            <span className="truncate flex-1 min-w-0 font-sans">{node.name}</span>
          </button>

          {!isCollapsed && (
            <div className="space-y-0.5 animate-in fade-in-50 slide-in-from-top-1 duration-150">
              {childrenKeys.map(key => renderSourceTreeNode(node.children[key], sourceId, depth + 1))}
            </div>
          )}
        </div>
      );
    } else {
      const isFileSelected = selectedFile === node.path;
      return (
        <button
          type="button"
          key={node.path}
          onClick={() => {
            handleFileSelect(node.path, undefined, String(sourceId));
            if (typeof window !== 'undefined' && window.innerWidth < 768) {
              setIsSidebarOpen(false);
            }
          }}
          className={cn(
            "w-full flex items-center gap-2 py-1 rounded text-[11px] transition-all text-left",
            isFileSelected
              ? (theme === 'dark' ? "bg-ds-indigo-500/10 text-ds-indigo-400 font-semibold" : "bg-ds-indigo-55 text-ds-indigo-750 font-semibold")
              : (theme === 'dark' ? "text-ds-zinc-500 hover:bg-ds-zinc-800/40 hover:text-ds-zinc-300" : "text-ds-zinc-550 hover:bg-ds-zinc-200/55 hover:text-ds-zinc-800")
          )}
          style={{ paddingLeft: `${Math.max(8, depth * 12 + 14)}px` }}
          title={node.path}
        >
          <FileText className="w-3 h-3 shrink-0 opacity-70" />
          <span className="truncate flex-1 min-w-0 font-mono">{node.name}</span>
        </button>
      );
    }
  };

  // Resize handler logic
  useEffect(() => {
    if (!isResizingSidebar) return;

    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = e.clientX;
      if (newWidth > 180 && newWidth < 500) {
        setSidebarWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      setIsResizingSidebar(false);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizingSidebar]);

  const startResizingSidebar = (mouseDownEvent: React.MouseEvent) => {
    mouseDownEvent.preventDefault();
    setIsResizingSidebar(true);
  };

  const toggleFolder = (path: string) => {
    setCollapsedFolders(prev => ({ ...prev, [path]: !prev[path] }));
  };

  const buildFileTree = (filePaths: string[]) => {
    const root: Record<string, any> = {};
    for (const filePath of filePaths) {
      const parts = filePath.split('/');
      let current = root;
      let currentPath = "";
      for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        currentPath = currentPath ? `${currentPath}/${part}` : part;
        const isLast = i === parts.length - 1;
        if (!current[part]) {
          current[part] = {
            name: part,
            path: currentPath,
            type: isLast ? 'file' : 'folder',
            children: isLast ? undefined : {}
          };
        }
        if (!isLast) {
          current = current[part].children;
        }
      }
    }
    return root;
  };

  return (
    <motion.aside
      animate={{ width: isSidebarOpen ? sidebarWidth : 0 }}
      transition={isResizingSidebar ? { type: "tween", duration: 0 } : { type: "spring", stiffness: 300, damping: 30 }}
      className={cn(
          "h-full border-r flex flex-col transition-all duration-150 overflow-hidden",
          "fixed md:relative top-0 left-0 md:top-auto md:left-auto z-50 md:z-30",
          theme === 'dark' ? "bg-ds-zinc-950 border-ds-zinc-700" : "bg-ds-zinc-100 border-ds-zinc-300",
          !isSidebarOpen ? "pointer-events-none border-none" : "pointer-events-auto"
      )}
    >
      <AnimatePresence>
        {isSidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col h-full overflow-hidden"
            style={{ width: `${sidebarWidth}px` }}
          >
            <div className={cn(
              "hidden md:flex h-16 px-4 items-center justify-between border-b shrink-0",
              theme === 'dark' ? "border-ds-zinc-800" : "border-ds-zinc-300"
            )}>
              <DoctusLogo theme={theme} />
              <span className="doctus-kicker text-ds-zinc-500">Workspace</span>
            </div>
            {/* Sidebar Header */}
            <div className="px-4 pt-4 pb-2 flex md:hidden items-center justify-end shrink-0">
              {/* Mobile Close Button */}
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsSidebarOpen(false)}
                className={cn(
                  "h-7 w-7 rounded-lg border transition-all flex items-center justify-center",
                  theme === 'dark'
                    ? "text-ds-zinc-400 border-ds-zinc-800 hover:text-ds-zinc-200 hover:bg-ds-zinc-800"
                    : "text-ds-zinc-500 border-ds-zinc-200 hover:text-ds-zinc-900 hover:bg-ds-zinc-100"
                )}
                title={t('sidebar.closeMenuTitle')}
              >
                <X className="w-3.5 h-3.5" />
              </Button>
            </div>

            {/* Action Buttons (New Chat) */}
            <div className="p-4 space-y-2 border-b border-ds-zinc-800">
              <Button
                onClick={() => {
                  startNewChat();
                  if (typeof window !== 'undefined' && window.innerWidth < 768) {
                    setIsSidebarOpen(false);
                  }
                }}
                id="sidebar-new-chat-btn"
                className="w-full justify-between gap-3 h-11 rounded-md bg-primary hover:brightness-105 text-primary-foreground border-0 transition-all duration-150"
              >
                <Plus className="w-4 h-4" />
                  <span className="text-[10px] font-mono font-semibold uppercase tracking-[0.14em]">{t('sidebar.newChat')}</span>
              </Button>
            </div>

            {/* History & Active Project Files */}
            <div className="flex-1 flex flex-col overflow-hidden min-h-0">
              {/* Verlauf Section */}
              <div className={cn("flex flex-col overflow-hidden transition-all duration-300 min-h-0",
                isHistoryExpanded ? "flex-1 max-h-[75%]" : "h-auto shrink-0"
              )}>
                <div
                  onClick={() => setIsHistoryExpanded(!isHistoryExpanded)}
                  className={cn(
                    "flex items-center justify-between px-4 py-2.5 select-none cursor-pointer transition-colors shrink-0 font-bold text-[10px] uppercase tracking-[0.12em]",
                    theme === 'dark'
                      ? "text-ds-zinc-400 hover:bg-ds-zinc-900/60 bg-ds-zinc-900/10"
                      : "text-ds-zinc-500 hover:bg-ds-zinc-200/45 bg-ds-zinc-50/20"
                  )}
                >
                  <span className="flex items-center gap-2">
                    <ChevronDown className={cn("w-3.5 h-3.5 transition-transform duration-200", !isHistoryExpanded && "-rotate-90")} />
                    <span>{t('sidebar.history')}</span>
                  </span>
                  <span className={cn(
                    "text-[9px] font-mono px-1.5 py-0.5 rounded-sm",
                    theme === 'dark' ? "bg-ds-zinc-800/80 text-ds-zinc-400" : "bg-ds-zinc-200/70 text-ds-zinc-600"
                  )}>
                    {sessions.filter(session => {
                      if (selectedProject) {
                        return session.project_id === selectedProject.id;
                      } else {
                        return !session.project_id;
                      }
                    }).length}
                  </span>
                </div>

                {isHistoryExpanded && (
                  <ScrollArea className="flex-1 px-3 py-1.5">
                    <div className="space-y-0.5">
                       {sessions.filter(session => {
                         if (selectedProject) {
                           return session.project_id === selectedProject.id;
                         } else {
                           return !session.project_id;
                         }
                       }).map(session => (
                        <div
                          key={session.id}
                          id={`sidebar-session-item-${session.id}`}
                          onClick={() => {
                            handleSessionSelect(session);
                            if (typeof window !== 'undefined' && window.innerWidth < 768) {
                              setIsSidebarOpen(false);
                            }
                          }}
                          className={cn(
                            "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs transition-all group relative font-medium cursor-pointer",
                            activeSessionId === session.id
                              ? (theme === 'dark' ? "bg-ds-zinc-855 text-ds-zinc-150" : "bg-ds-zinc-200/75 text-ds-zinc-950")
                              : (theme === 'dark' ? "text-ds-zinc-400 hover:bg-ds-zinc-800 hover:text-ds-zinc-200" : "text-ds-zinc-600 hover:bg-ds-zinc-200/50 hover:text-ds-zinc-900")
                          )}
                        >
                          <MessageSquare className="w-3.5 h-3.5 text-ds-zinc-500 shrink-0" />
                          <span className="truncate text-left flex-1">{session.title}</span>
                          <button
                            type="button"
                            onClick={(e) => handleRemoveSession(session.id, e)}
                            id={`sidebar-remove-session-${session.id}`}
                            className={cn(
                              "absolute right-2 p-1 rounded opacity-0 group-hover:opacity-100 transition-all",
                              theme === 'dark' ? "hover:bg-ds-zinc-700 text-ds-zinc-600 hover:text-ds-zinc-400" : "hover:bg-ds-zinc-200 text-ds-zinc-400 hover:text-ds-zinc-600"
                            )}
                            title={t('sidebar.deleteSessionTitle')}
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      ))}
                      </div>
                    </ScrollArea>
                  )}
                </div>

              {/* Pinned folders / Knowledge sources */}
              {(() => {
                const pinnedSources = connectedSources
                  .filter(src => {
                    // Global sources (project_id null) are relevant inside every
                    // project context (chat retrieval merges them too, see
                    // backend/services/search.py), but project-specific sources
                    // must stay invisible outside their own project.
                    const matchesProject = selectedProject
                      ? (src.project_id === selectedProject.id || !src.project_id)
                      : !src.project_id;
                    return matchesProject && pinnedSourceIds.includes(src.id);
                  })
                  .slice(0, 4);

                return (
                  <div
                    className={cn(
                      "flex flex-col border-t transition-all duration-300 min-h-0 mt-auto shrink-0",
                      expandedFolderId !== null ? "max-h-[50%]" : "max-h-[33%]"
                    )}
                    style={{ borderColor: theme === 'dark' ? 'rgb(var(--ds-neutral-700))' : 'rgb(var(--ds-neutral-200))' }}
                  >
                    <div className={cn(
                      "flex items-center justify-between px-4 py-2.5 select-none border-b shrink-0 font-bold text-[10px] uppercase tracking-[0.12em]",
                      theme === 'dark' ? "text-ds-zinc-400 bg-ds-zinc-900/10 border-ds-zinc-800/60" : "text-ds-zinc-500 bg-ds-zinc-50/20 border-ds-zinc-200"
                    )}>
                      <span>{t('sidebar.knowledgeSources')}</span>
                      <span className={cn(
                        "text-[9px] font-mono px-1.5 py-0.5 rounded-sm",
                        theme === 'dark' ? "bg-ds-zinc-850 text-ds-zinc-450" : "bg-ds-zinc-200 text-ds-zinc-500"
                      )}>
                        {pinnedSources.length}
                      </span>
                    </div>

                    <ScrollArea className="flex-1 px-3 py-2">
                      <div className="space-y-1.5">
                        {pinnedSources.length === 0 ? (
                          <div className="text-[10px] text-ds-zinc-500 italic py-3 text-center">
                            {t('sidebar.noPinnedSources')}
                          </div>
                        ) : (
                          pinnedSources.map(source => {
                            const isLocal = source.type?.toLowerCase() === 'local';
                            const isExpanded = expandedFolderId === source.id;
                            const filesList = sourceFiles[source.id] || [];
                            const isLoadingFiles = loadingSourceId === source.id;
                            const isSelected = isLocal && selectedDoc?.id === source.id;

                            if (isLocal) {
                              return (
                                <div
                                  key={source.id}
                                  className={cn(
                                    "rounded-lg border transition-all overflow-hidden",
                                    theme === 'dark'
                                      ? (isSelected ? "bg-ds-zinc-900 border-ds-zinc-800" : "bg-ds-zinc-950 border-ds-zinc-800 hover:bg-ds-zinc-900" )
                                      : (isSelected ? "bg-ds-zinc-50 border-ds-zinc-200" : "bg-ds-white border-ds-zinc-200 hover:bg-ds-zinc-50")
                                  )}
                                >
                                  <button
                                    type="button"
                                    onClick={() => {
                                      handleFileSelect(source.name, undefined, String(source.id));
                                      if (typeof window !== 'undefined' && window.innerWidth < 768) {
                                        setIsSidebarOpen(false);
                                      }
                                    }}
                                    className="w-full flex items-center px-3 py-2 text-xs font-semibold text-left select-none cursor-pointer"
                                  >
                                    <div className="flex items-center gap-2 min-w-0 flex-1">
                                      <FileText className="w-3.5 h-3.5 text-ds-indigo-500 shrink-0" />
                                      <span className={cn("truncate", theme === 'dark' ? "text-ds-zinc-300" : "text-ds-zinc-700")}>
                                        {source.name}
                                      </span>
                                      {selectedProject && !source.project_id && (
                                        <span className={cn(
                                          "shrink-0 text-[8px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-sm",
                                          theme === 'dark' ? "bg-ds-indigo-500/15 text-ds-indigo-300" : "bg-ds-indigo-100 text-ds-indigo-600"
                                        )}>
                                          {t('sidebar.globalSourceBadge') || 'Global'}
                                        </span>
                                      )}
                                    </div>
                                  </button>
                                </div>
                              );
                            }

                            return (
                              <div
                                key={source.id}
                                className={cn(
                                  "rounded-lg border transition-all overflow-hidden",
                                  theme === 'dark'
                                    ? (isExpanded ? "bg-ds-zinc-900 border-ds-zinc-800" : "bg-ds-zinc-950 border-ds-zinc-800 hover:bg-ds-zinc-900" )
                                    : (isExpanded ? "bg-ds-zinc-50 border-ds-zinc-200" : "bg-ds-white border-ds-zinc-200 hover:bg-ds-zinc-50")
                                )}
                              >
                                <button
                                  type="button"
                                  onClick={() => {
                                    if (isExpanded) {
                                      setExpandedFolderId(null);
                                    } else {
                                      setExpandedFolderId(source.id);
                                      if (!sourceFiles[source.id]) {
                                        loadSourceFiles(source.id);
                                      }
                                    }
                                  }}
                                  className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-left select-none cursor-pointer"
                                >
                                  <div className="flex items-center gap-2 min-w-0 flex-1">
                                    <Folder className="w-3.5 h-3.5 text-ds-indigo-500 shrink-0" />
                                    <span className={cn("truncate", theme === 'dark' ? "text-ds-zinc-300" : "text-ds-zinc-700")}>
                                      {source.name}
                                    </span>
                                    {selectedProject && !source.project_id && (
                                      <span className={cn(
                                        "shrink-0 text-[8px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-sm",
                                        theme === 'dark' ? "bg-ds-indigo-500/15 text-ds-indigo-300" : "bg-ds-indigo-100 text-ds-indigo-600"
                                      )}>
                                        {t('sidebar.globalSourceBadge') || 'Global'}
                                      </span>
                                    )}
                                  </div>
                                  <span className="shrink-0 ml-1">
                                    {isExpanded ? (
                                      <ChevronDown className="w-3.5 h-3.5 text-ds-zinc-500" />
                                    ) : (
                                      <ChevronRight className="w-3.5 h-3.5 text-ds-zinc-500" />
                                    )}
                                  </span>
                                </button>

                                {isExpanded && (
                                  <div className="px-2 pb-2 border-t pt-1.5 space-y-1" style={{ borderColor: theme === 'dark' ? 'rgba(63, 63, 70, 0.4)' : 'rgba(228, 228, 231, 0.6)' }}>
                                    {isLoadingFiles ? (
                                      <div className="flex items-center gap-1.5 px-2 py-3 text-[10px] text-ds-zinc-500 font-medium">
                                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                        <span>{t('sidebar.loadingFiles')}</span>
                                      </div>
                                    ) : filesList.length === 0 ? (
                                      <div className="text-[10px] text-ds-zinc-500 italic px-2 py-3 text-center">
                                        {t('sidebar.noFiles')}
                                      </div>
                                    ) : (
                                      <div className="max-h-[300px] overflow-y-auto space-y-0.5 pr-1">
                                        {(() => {
                                          const fileTree = buildFileTree(filesList);
                                          const rootKeys = Object.keys(fileTree).sort((a, b) => {
                                            const typeA = fileTree[a].type;
                                            const typeB = fileTree[b].type;
                                            if (typeA === typeB) return a.localeCompare(b);
                                            return typeA === 'folder' ? -1 : 1;
                                          });
                                          return rootKeys.map(key => renderSourceTreeNode(fileTree[key], source.id, 0));
                                        })()}
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })
                        )}
                      </div>
                    </ScrollArea>
                  </div>
                );
              })()}
            </div>

            {/* Sidebar Footer Controls */}
            <div className={cn(
              "p-4 border-t space-y-3.5 z-20 transition-colors duration-200",
              theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800" : "bg-ds-zinc-100 border-ds-zinc-200"
            )}>
              <div className="flex items-center justify-between pt-1">
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  {/* Avatar */}
                  <div className="h-8 w-8 rounded-md border border-ds-indigo-500 bg-ds-indigo-500/10 flex items-center justify-center text-ds-indigo-400 font-mono font-bold text-[10px] shrink-0">
                    ID
                  </div>
                  {/* User info */}
                  <div className="min-w-0">
                    <p className={cn("text-xs font-semibold truncate leading-none mb-1", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-800")}>
                      Doctwos Nutzer
                    </p>
                    <p className="text-[9px] font-medium text-ds-zinc-500 leading-none truncate">
                      Lokale Sitzung
                    </p>
                  </div>
                </div>

                {/* Log Out button */}
                <Button
                  variant="ghost"
                  size="icon"
                  id="logout-btn"
                  onClick={handleLogout}
                  className={cn(
                    "h-7 w-7 rounded-lg transition-all",
                    theme === 'dark' ? "text-ds-zinc-500 hover:text-ds-zinc-300 hover:bg-ds-zinc-800" : "text-ds-zinc-500 hover:text-ds-zinc-900 hover:bg-ds-zinc-200/50"
                  )}
                  title={t('sidebar.logoutTitle')}
                >
                  <LogOut className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {isSidebarOpen && (
        <div
          onMouseDown={startResizingSidebar}
          className={cn(
            "absolute top-0 right-0 w-1.5 h-full cursor-col-resize z-50 transition-colors duration-150 hover:bg-ds-indigo-500/20 active:bg-ds-indigo-500/40",
            isResizingSidebar && "bg-ds-indigo-500/30 w-1"
          )}
        />
      )}
    </motion.aside>
  );
}
