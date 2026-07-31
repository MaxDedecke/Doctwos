"use client";

import React, { useEffect, useRef, useState } from 'react';
import { Search, X, Loader2, FileCode, FileText, Folder, Database, Menu, Network, Link2, Settings, Sun, Moon, Plus, ChevronDown, Filter } from 'lucide-react';
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api } from "@/app/services/api";
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useFeatures } from '@/lib/FeaturesContext';
import { DoctusIcon } from './Logo';

interface SearchResult {
  node_type: string;
  node_id: number;
  node_label: string;
  node_url: string | null;
  node_meta: Record<string, any>;
}

interface GlobalSearchProps {
  theme: string;
  setTheme: (theme: string) => void;
  projects: any[];
  connectedSources: any[];
  onSelectResult: (result: SearchResult) => void;
  isSidebarOpen: boolean;
  setIsSidebarOpen: (val: boolean) => void;
  setIsSettingsOpen: (val: boolean) => void;
  setIsLinkManagerOpen: (val: boolean) => void;
  onOpenGraphView: () => void;
  panelConfigs: string[];
  onAddPanel: (type: string) => void;
  selectedProject: any;
  onProjectSelect: (project: any) => void;
}

const ADD_VIEW_TYPES = ['chat', 'code', 'doc', 'graph', 'webview'] as const;

const GROUP_ORDER = ['entity', 'document', 'project', 'knowledge_source'];
const GROUP_ICONS: Record<string, any> = {
  entity: FileCode,
  document: FileText,
  project: Folder,
  knowledge_source: Database,
};

export function GlobalSearch({
  theme,
  setTheme,
  projects,
  connectedSources,
  onSelectResult,
  isSidebarOpen,
  setIsSidebarOpen,
  setIsSettingsOpen,
  setIsLinkManagerOpen,
  onOpenGraphView,
  panelConfigs,
  onAddPanel,
  selectedProject,
  onProjectSelect
}: GlobalSearchProps) {
  const { t } = useLanguage();
  const features = useFeatures();
  const [isAddViewOpen, setIsAddViewOpen] = useState(false);

  const toggleTheme = () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    localStorage.setItem('doctus-theme', newTheme);
  };

  const [query, setQuery] = useState('');
  const [scope, setScope] = useState(selectedProject ? 'current' : 'all');
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [activeIndex, setActiveIndex] = useState(-1);
  const [limit, setLimit] = useState(6);

  const filteredSources = React.useMemo(() => {
    return connectedSources.filter(src => {
      return !selectedProject || !src.project_id || src.project_id === selectedProject.id;
    });
  }, [connectedSources, selectedProject]);

  // Switching the current project resets the search scope back to the
  // project-appropriate default ("nur dieses Projekt" / "alle Projekte" in
  // Allgemein-Modus) instead of silently keeping a stale scope from before
  // the switch — mirrors how chat re-scopes retrieval on project change.
  const prevProjectIdRef = useRef<number | null>(selectedProject?.id ?? null);
  useEffect(() => {
    const currId = selectedProject?.id ?? null;
    if (prevProjectIdRef.current !== currId) {
      prevProjectIdRef.current = currId;
      setScope(selectedProject ? 'current' : 'all');
    }
  }, [selectedProject]);

  // A source-scoped search becomes invalid if that source disappears from
  // the (project-filtered) source list, e.g. after a project switch. Done
  // during render (guarded by a state comparison, not a ref — refs can't be
  // read/written during render) rather than in an effect, same
  // "adjusting state" idiom as prevProjectIdRef above but state-based.
  const [prevFilteredSources, setPrevFilteredSources] = useState(filteredSources);
  if (prevFilteredSources !== filteredSources) {
    setPrevFilteredSources(filteredSources);
    const [scopeKind, scopeIdRaw] = scope.split(':');
    if (scopeKind === 'source') {
      const scopeId = scopeIdRaw ? parseInt(scopeIdRaw, 10) : null;
      const stillValid = filteredSources.some(src => src.id === scopeId);
      if (!stillValid) {
        setScope(selectedProject ? 'current' : 'all');
      }
    }
  }

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // --- Keyboard Shortcuts ---
  // Ctrl/Cmd+K focuses the search from anywhere in the app (Spotlight-style)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  // Close search results when clicking outside
  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  // Reset limit to 6 when query or scope changes — done during render
  // (guarded by state comparisons) rather than in an effect.
  const [prevQuery, setPrevQuery] = useState(query);
  const [prevScope, setPrevScope] = useState(scope);
  if (prevQuery !== query || prevScope !== scope) {
    setPrevQuery(query);
    setPrevScope(scope);
    setLimit(6);
  }

  // --- Search Logic with Debouncing and Lazy Pagination ---
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!query.trim()) {
      (() => {
        setResults([]);
        setCounts({});
        setIsLoading(false);
      })();
      return;
    }

    const performCall = () => {
      // Abort previous request if one is still running
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsLoading(true);

      const [scopeKind, scopeIdRaw] = scope.split(':');
      const scopeId = scopeIdRaw ? parseInt(scopeIdRaw, 10) : undefined;

      api.searchGlobal(query.trim(), {
        projectId: scopeKind === 'current' ? selectedProject?.id : undefined,
        sourceId: scopeKind === 'source' ? scopeId : undefined,
        types: scopeKind === 'source' ? 'document' : undefined,
        limit: limit,
        signal: controller.signal,
      })
        .then(res => {
          setResults(res.data.results || []);
          setCounts(res.data.counts || {});
          setActiveIndex(-1);
        })
        .catch(err => {
          if (err.name !== 'CanceledError' && err.name !== 'AbortError') {
            console.error('Search failed', err);
          }
        })
        .finally(() => setIsLoading(false));
    };

    // If limit is 6, it's a new query/scope typing (use debounce)
    // If limit > 6, the user scrolled to the bottom (load immediately)
    if (limit === 6) {
      debounceRef.current = setTimeout(performCall, 300);
    } else {
      performCall();
    }

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, scope, limit, selectedProject]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    // Check if scrolled near the bottom (within 20px)
    const isAtBottom = target.scrollHeight - target.scrollTop <= target.clientHeight + 20;
    if (isAtBottom && !isLoading) {
      // Check if there are more results to fetch in any category
      const hasMore = Object.keys(counts).some(type => {
        const currentCount = results.filter(r => r.node_type === type).length;
        return (counts[type] || 0) > currentCount;
      });
      if (hasMore) {
        setLimit(prev => prev + 10);
      }
    }
  };

  const grouped = GROUP_ORDER
    .map(type => ({ type, items: results.filter(r => r.node_type === type) }))
    .filter(g => g.items.length > 0);
  const flatForKeyboard = grouped.flatMap(g => g.items);

  const handleSelect = (result: SearchResult) => {
    onSelectResult(result);
    setIsOpen(false);
    setQuery('');
    setResults([]);
    inputRef.current?.blur();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen || flatForKeyboard.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex(prev => Math.min(prev + 1, flatForKeyboard.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(prev => Math.max(prev - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const target = flatForKeyboard[activeIndex >= 0 ? activeIndex : 0];
      if (target) handleSelect(target);
    } else if (e.key === 'Escape') {
      setIsOpen(false);
      inputRef.current?.blur();
    }
  };

  return (
    <div
      ref={containerRef}
      className={cn(
        "h-12 shrink-0 w-full flex items-center gap-3 px-3 border-b relative z-40 transition-all duration-300",
        theme === 'dark' ? "bg-zinc-950/90 border-zinc-800" : "bg-white/90 border-zinc-200"
      )}
    >
      <Button
        variant="ghost"
        size="icon"
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
        className={cn(
          "h-8 w-8 rounded-lg border transition-all duration-200 shrink-0 group",
          theme === 'dark'
            ? "bg-zinc-900/50 border-zinc-800 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800"
            : "bg-zinc-50 border-zinc-200 text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
        )}
      >
        <DoctusIcon className="h-5 w-5 block group-hover:hidden filter drop-shadow-[0_0_8px_rgba(77,127,255,0.15)]" />
        <Menu className="w-4 h-4 hidden group-hover:block" />
      </Button>

      {/* Project Selector */}
      <div className="flex items-center gap-3 select-none shrink-0">
        <Select
          value={selectedProject ? String(selectedProject.id) : "general"}
          onValueChange={(val) => {
            if (val === "general") {
              onProjectSelect(null);
            } else {
              const proj = projects.find(p => String(p.id) === val);
              if (proj) onProjectSelect(proj);
            }
          }}
        >
          <SelectTrigger id="project-selector" className={cn(
            "h-8 text-xs border rounded-lg w-auto min-w-[155px] max-w-[220px] font-semibold px-2.5 gap-2",
            theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-200" : "bg-white border-zinc-200 text-zinc-800"
          )}>
            <SelectValue placeholder={t('page.generalContext') || "Allgemein"} />
          </SelectTrigger>
          <SelectContent className={theme === 'dark' ? "bg-zinc-950 border-zinc-900 text-zinc-200" : "bg-white border-zinc-200 text-zinc-850"}>
            <SelectItem value="general" className="text-xs">
              {t('page.generalContext') || "Allgemein (nicht projektspezifisch)"}
            </SelectItem>
            {projects.filter(p => !p.is_archived).map(p => (
              <SelectItem key={p.id} value={String(p.id)} className="text-xs">
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {features.views.globalSearch ? (
      <>
      <div className="relative flex-1 max-w-xl">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setIsOpen(true); }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={t('globalSearch.placeholder')}
          className={cn(
            "w-full border rounded-lg pl-8 pr-8 py-1.5 text-xs focus:outline-none transition-all font-sans",
            theme === 'dark'
              ? "bg-zinc-900 border-zinc-800 text-zinc-200 placeholder-zinc-600 focus:border-indigo-700"
              : "bg-zinc-50 border-zinc-200 text-zinc-800 placeholder-zinc-400 focus:border-indigo-300"
          )}
        />
        {isLoading ? (
          <Loader2 className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500 animate-spin" />
        ) : query && (
          <button
            onClick={() => { setQuery(''); setResults([]); inputRef.current?.focus(); }}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}

        {isOpen && query.trim() && (
          <div className={cn(
            "absolute left-0 right-0 top-full mt-1.5 rounded-lg border shadow-2xl overflow-hidden",
            theme === 'dark' ? "bg-zinc-900 border-zinc-800" : "bg-white border-zinc-200"
          )}>
            <div 
              className="max-h-96 overflow-y-auto pr-1 select-none scrollbar-thin scrollbar-thumb-zinc-200 dark:scrollbar-thumb-zinc-800 scrollbar-track-transparent"
              onScroll={handleScroll}
            >
              {grouped.length === 0 && !isLoading && (
                <div className="px-3 py-4 text-xs text-zinc-500 text-center">{t('globalSearch.noResultsFor', { query })}</div>
              )}
              {grouped.map(group => {
                const Icon = GROUP_ICONS[group.type];
                return (
                  <div key={group.type} className="py-1">
                    <div className={cn(
                      "px-3 py-1 text-[9px] font-bold uppercase tracking-wider",
                      theme === 'dark' ? "text-zinc-500" : "text-zinc-400"
                    )}>
                      {t(`globalSearch.groups.${group.type}`)}
                    </div>
                    {group.items.map(item => {
                      const flatIdx = flatForKeyboard.indexOf(item);
                      const active = flatIdx === activeIndex;
                      return (
                        <button
                          key={`${item.node_type}-${item.node_id}`}
                          onClick={() => handleSelect(item)}
                          onMouseEnter={() => setActiveIndex(flatIdx)}
                          className={cn(
                            "w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left transition-colors",
                            active
                              ? (theme === 'dark' ? "bg-indigo-500/15 text-indigo-300" : "bg-indigo-50 text-indigo-700")
                              : (theme === 'dark' ? "text-zinc-300 hover:bg-zinc-800/60" : "text-zinc-700 hover:bg-zinc-50")
                          )}
                        >
                          <Icon className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
                          <span className="flex flex-col min-w-0 flex-1">
                            <span className="truncate">{item.node_label}</span>
                            {item.node_type === 'entity' && item.node_meta?.file_path && (
                              <span className="text-[10px] text-zinc-500 truncate">{item.node_meta.file_path}</span>
                            )}
                          </span>
                        </button>
                      );
                    })}
                    {(counts[group.type] || 0) > group.items.length && (
                      <div className="px-3 py-1 text-[10px] text-zinc-500">
                        {t('globalSearch.moreResults', { count: counts[group.type] - group.items.length })}
                      </div>
                    )}
                  </div>
                );
              })}
              {isLoading && limit > 6 && (
                <div className="flex justify-center items-center py-2.5 text-zinc-500 gap-1.5 text-[10px] border-t dark:border-zinc-800/60 border-zinc-100">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-zinc-400" />
                  <span>{t('common.loading')}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <Select value={scope} onValueChange={setScope}>
        <SelectTrigger className={cn(
          "h-8 w-8 p-0 flex items-center justify-center border rounded-lg shrink-0 [&>svg:last-child]:hidden",
          theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-300" : "bg-white border-zinc-200 text-zinc-700"
        )} title={t('globalSearch.filterTitle') || 'Suchbereich filtern'}>
          <Filter className="h-3.5 w-3.5" />
        </SelectTrigger>
        <SelectContent className={theme === 'dark' ? "bg-zinc-900 border-zinc-800 text-zinc-200" : "bg-white border-zinc-200 text-zinc-800"}>
          {selectedProject && (
            <SelectItem value="current" className="text-xs">{t('globalSearch.currentProjectScope')}</SelectItem>
          )}
          <SelectItem value="all" className="text-xs">{t('globalSearch.allScope')}</SelectItem>
          {filteredSources.length > 0 && (
            <>
              <div className="text-[9px] font-bold px-2 py-1 uppercase tracking-wider text-zinc-500 mt-1">{t('globalSearch.groups.knowledge_source')}</div>
              {filteredSources.map(s => (
                <SelectItem key={`source-${s.id}`} value={`source:${s.id}`} className="text-xs">{s.name}</SelectItem>
              ))}
            </>
          )}
        </SelectContent>
      </Select>
      </>
      ) : (
        <div className="flex-1" />
      )}

      {/* Global header actions — add view, knowledge graph, link manager, theme & settings */}
      <div className="flex items-center gap-1.5 shrink-0 ml-auto pl-1">
        {/* Add view dropdown — pick which view to open */}
        <div className="relative">
          <Button
            size="sm"
            variant="outline"
            disabled={panelConfigs.length >= 4}
            onClick={() => setIsAddViewOpen(o => !o)}
            title={panelConfigs.length >= 4 ? t('page.workspace.maxViewsReached') : t('page.workspace.addView')}
            className={cn(
              "text-[10px] h-8 px-3 rounded-lg font-bold gap-1.5 transition-all cursor-pointer border",
              panelConfigs.length >= 4
                ? "bg-zinc-900 border-zinc-850 text-zinc-600"
                : (theme === 'dark'
                    ? "bg-zinc-900 border-zinc-800 text-zinc-100 hover:bg-zinc-800 hover:text-white"
                    : "bg-white border-zinc-200 text-zinc-950 hover:bg-zinc-50 hover:text-black")
            )}
          >
            <Plus className="w-3.5 h-3.5" />
            <span className="hidden lg:inline">{t('page.workspace.addView')}</span>
            <ChevronDown className={cn("w-3.5 h-3.5 transition-transform", isAddViewOpen && "rotate-180")} />
          </Button>

          {isAddViewOpen && panelConfigs.length < 4 && (
            <>
              <div className="fixed inset-0 z-[90]" onClick={() => setIsAddViewOpen(false)} />
              <div className={cn(
                "absolute right-0 mt-2 w-52 z-[100] rounded-lg border shadow-2xl overflow-hidden py-1.5",
                theme === 'dark' ? "bg-zinc-950 border-zinc-800 shadow-black/60" : "bg-white border-zinc-200 shadow-zinc-200"
              )}>
                <div className={cn(
                  "px-3 py-1.5 text-[9px] font-bold uppercase tracking-wider",
                  theme === 'dark' ? "text-zinc-500" : "text-zinc-400"
                )}>
                  {t('page.workspace.addViewMenuTitle')}
                </div>
                {/* Unlike code/doc/graph, a 'chat' panel isn't backed by per-panel
                    state (see page.tsx's renderPanel — chatMessages/activeSessionId
                    are global, not indexed by panel), so a second one would just
                    mirror the first and can never be closed. Hide it once one exists. */}
                {ADD_VIEW_TYPES.filter(type => type !== 'chat' || !panelConfigs.includes('chat')).map((type) => (
                  <button
                    key={type}
                    onClick={() => { onAddPanel(type); setIsAddViewOpen(false); }}
                    className={cn(
                      "w-full text-left px-3 py-2 text-xs font-medium flex items-center gap-2 transition-colors cursor-pointer",
                      theme === 'dark' ? "text-zinc-200 hover:bg-zinc-900" : "text-zinc-800 hover:bg-zinc-50"
                    )}
                  >
                    {t(`page.viewTypes.${type}`)}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {features.views.knowledgeGraph && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onOpenGraphView}
            className={cn(
              "h-8 w-8 rounded-lg border transition-all duration-200",
              theme === 'dark'
                ? "text-zinc-400 border-zinc-800 hover:text-zinc-100 hover:bg-zinc-900"
                : "text-zinc-800 border-zinc-200 hover:text-zinc-950 hover:bg-zinc-100"
            )}
            title={t('sidebar.knowledgeGraphTitle')}
          >
            <Network className="w-4 h-4" />
          </Button>
        )}

        {features.views.linkManager && (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setIsLinkManagerOpen(true)}
            className={cn(
              "h-8 w-8 rounded-lg border transition-all duration-200",
              theme === 'dark'
                ? "bg-zinc-900/50 border-zinc-800 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800"
                : "bg-zinc-50 border-zinc-200 text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
            )}
            title={t('sidebar.linkManagerTitle')}
          >
            <Link2 className="w-4 h-4" />
          </Button>
        )}

        <Button
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          className={cn(
            "h-8 w-8 rounded-lg border transition-all duration-200",
            theme === 'dark'
              ? "bg-zinc-900/50 border-zinc-800 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800"
              : "bg-zinc-50 border-zinc-200 text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
          )}
          title={theme === 'dark' ? t('globalSearch.toLightModeTitle') : t('globalSearch.toDarkModeTitle')}
        >
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </Button>

        <Button
          variant="ghost"
          size="icon"
          id="settings-btn"
          onClick={() => setIsSettingsOpen(true)}
          className={cn(
            "h-8 w-8 rounded-lg border transition-all duration-200",
            theme === 'dark'
              ? "bg-zinc-900/50 border-zinc-800 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800"
              : "bg-zinc-50 border-zinc-200 text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
          )}
          title={t('sidebar.settingsTitle')}
        >
          <Settings className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}
