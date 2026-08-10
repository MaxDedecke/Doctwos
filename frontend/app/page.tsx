"use client";

import React, { useState, useEffect, useRef } from 'react';
import Editor from '@monaco-editor/react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  MessageSquare,
  Folder,
  Code,
  Send,
  Menu,
  History,
  Terminal,
  Lock,
  RefreshCw,
  Database,
  Search,
  MoreVertical,
  Layers,
  Sparkles,
  HelpCircle,
  Clock,
  BookOpen,
  FileText,
  FileCode,
  Trash2,
  Download,
  Share2,
  X,
  Check,
  ExternalLink,
  Loader2,
  Activity,
  Github,
  LogOut,
  Globe,
  Key,
  GitBranch,
  Network,
  ChevronRight,
  ChevronLeft,
  Box,
  Braces,
  Link2
} from 'lucide-react';

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { api, API_URL } from './services/api';
import { SettingsModal } from "@/components/SettingsModal";
import { SettingsProvider } from "@/components/settings/SettingsContext";
import { LinkManagerView } from "@/components/LinkManagerView";
import { SplitPaneWorkspace } from "@/components/SplitPaneWorkspace";
import { LoginView } from "@/components/LoginView";
import { Sidebar } from "@/components/Sidebar";
import { ChatView } from "@/components/ChatView";
import { GlobalSearch } from "@/components/GlobalSearch";
import { CallGraphView } from "@/components/CallGraphView";
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { Suspense } from 'react';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { FeaturesProvider, useFeatures } from '@/lib/FeaturesContext';



// --- Main App Component ---

// File-extension buckets that decide which panel type a selection "belongs" to —
// shared between handleFileSelect (which view opens) and the unfrozen-panel sync
// effect (which already-open views follow along).
const DOC_FILE_RE = /\.(pdf|docx?|png|jpe?g)$/i;

// null = no selection at all (applies everywhere, e.g. to clear all panels).
function getSelectionViewType(path: string | null, doc: any | null): string | null {
  if (doc?.isWebOrigin) return 'webview';
  const name = path || doc?.name || null;
  if (!name) return null;
  const cleanName = name.split('#')[0];
  if (DOC_FILE_RE.test(cleanName)) return 'doc';
  return 'code';
}

// Shared by handleFileSelect and handlePanelFileSelect: figures out what kind of
// thing a bare (path, sourceId) reference actually points at — a locally-connected
// document (matched by filename against connectedSources), a live web-origin source
// (Confluence/Jira) oder eine gewöhnliche Code-/Dokumentdatei — so öffnen beide Aufrufstellen
// the same panel type for the same reference instead of drifting apart.
function resolveReferenceTarget(path: string | null, sourceId: any, connectedSources: any[] | null) {
  const cleanPath = path ? path.split('#')[0] : null;
  let resolvedSourceId = sourceId;
  if (!resolvedSourceId && cleanPath && connectedSources) {
    const clickedFilename = cleanPath.split('/').pop()?.toLowerCase();
    let cleanClickedFilename = clickedFilename;
    const prefixMatch = clickedFilename?.match(/^\d+_(.+)$/);
    if (prefixMatch) {
      cleanClickedFilename = prefixMatch[1];
    }
    const matchedSource = connectedSources.find(src => {
      if (src.type?.toLowerCase() !== 'local') return false;
      const srcFilename = src.name?.toLowerCase();
      const spacesFilename = src.spaces?.filename?.toLowerCase();
      return srcFilename === cleanClickedFilename || spacesFilename === cleanClickedFilename ||
             srcFilename === clickedFilename || spacesFilename === clickedFilename;
    });
    if (matchedSource) {
      resolvedSourceId = matchedSource.id;
    }
  }
  const matchedSource = resolvedSourceId && connectedSources ? connectedSources.find(src => src.id === resolvedSourceId) : null;
  const isWebOrigin = !!(matchedSource && (
    matchedSource.type?.toLowerCase() === 'confluence' ||
    matchedSource.type?.toLowerCase() === 'jira'
  ));
  return {
    isDoc: cleanPath ? DOC_FILE_RE.test(cleanPath) : false,
    isWebOrigin,
    resolvedSourceId,
  };
}

function AppContent() {
  const { t } = useLanguage();
  const features = useFeatures();

  // --- Authentication States ---
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isLoginInitialized, setIsLoginInitialized] = useState(false);
  const [currentUser, setCurrentUser] = useState<any | null>(null);

  // --- UI Layout & Sidebar States ---
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  useEffect(() => {
    // Session läuft über eine httpOnly-Cookie (lokale Anmeldung, siehe backend/api/auth.py)
    api.getMe()
      .then((res) => { setIsLoggedIn(true); setCurrentUser(res.data); })
      .catch(() => setIsLoggedIn(false))
      .finally(() => setIsLoginInitialized(true));

    // Collapse sidebar on mobile devices initially
    if (typeof window !== 'undefined') {
      const isMobile = window.innerWidth < 768;
      (() => setIsSidebarOpen(!isMobile))();
    }
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

  const handleLogout = async () => {
    try {
      await api.logout();
    } finally {
      // Auch wenn der Logout-Request scheitert: lokal ausloggen, damit der Nutzer
      // nicht in einer Sitzung festhängt, die er für beendet hält.
      setIsLoggedIn(false);
      setCurrentUser(null);
    }
  };

  const [isMobile, setIsMobile] = useState(false);
  const [activeMobileTab, setActiveMobileTab] = useState<'chat' | 'editor' | 'graph'>('chat');

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // --- Project & File States ---
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [selectedSource, setSelectedSource] = useState(null);
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedDoc, setSelectedDoc] = useState<any>(null);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const [activeRightTab, setActiveRightTab] = useState<'code' | 'doc' | 'weborigin' | 'graph'>('code');
  const [fileContent, setFileContent] = useState("");
  const [fileContentFormat, setFileContentFormat] = useState("text"); // 'text' | 'html' | 'markdown'
  const [isLoadingFile, setIsLoadingFile] = useState(false);
  const [branch, setBranch] = useState("main");

  // --- Chat & Session States ---
  const [chatMessages, setChatMessages] = useState([]);
  const [currentMessage, setCurrentMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessions, setSessions] = useState<any[]>([]);
  const [isSessionsLoaded, setIsSessionsLoaded] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [toast, setToast] = useState(null);

  // --- Analysis & AI Models ---
  const [activeLlmModel, setActiveLlmModel] = useState("qwen2.5:1.5b");
  const [activeEmbeddingModel, setActiveEmbeddingModel] = useState("nomic-embed-text");
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [temperature, setTemperature] = useState(0.7);
  const [systemPrompt, setSystemPrompt] = useState(
    "Du bist Doctus, ein Enterprise-Wissensassistent. Du hilfst dabei, große, gewachsene Projektlandschaften zu verstehen — "
    + "von COBOL-Beständen über Copybooks und JCL bis zu Dokumenten und angebundenen Wissensquellen (z. B. Confluence, Jira). "
    + "Antworte präzise und begründet, stütze dich ausschließlich auf die dir bereitgestellten und indexierten Inhalte, "
    + "und mache transparent, wenn dir Informationen fehlen oder unsicher sind."
  );
  const [llmProfiles, setLlmProfiles] = useState<any[]>([]);
  const [activeProfileId, setActiveProfileId] = useState<string>("ollama-default");

  // --- Settings & Design (Workspace Split) ---
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState('repos');
  const [theme, setTheme] = useState('dark');
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);
  const [workspaceSplit, setWorkspaceSplit] = useState("45/55");
  const [splitPercent, setSplitPercent] = useState(45);
  const [isDragging, setIsDragging] = useState(false);
  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartPercentRef = useRef(45);
  const splitContainerRef = useRef<HTMLDivElement>(null);
  const [isEditorMaximized, setIsEditorMaximized] = useState(false);
  // Only the chat opens on load — every other view opens on demand, triggered
  // by an explicit action (selecting a file/doc, clicking the graph icon, ...).
  const [panelConfigs, setPanelConfigs] = useState<string[]>(['chat']);
  const layoutMode =
    panelConfigs.length === 1 ? '1-pane' :
    panelConfigs.length === 2 ? 'split' :
    panelConfigs.length === 3 ? '3-col' :
    '4-grid';
  const [fileNavStack, setFileNavStack] = useState<Array<{file: string|null, doc: any|null, tab: 'code'|'doc'|'weborigin'|'graph'}>>([]);
  const isEditorNavigatingRef = useRef(false);
  const [editorFontSize, setEditorFontSize] = useState(13);
  const [editorMinimap, setEditorMinimap] = useState(true);
  const [editorFontFamily, setEditorFontFamily] = useState("'JetBrains Mono', monospace");

  // --- Entity & Metadata States ---
  const [projectEntities, setProjectEntities] = useState<any[]>([]);
  const [selectedEntity, setSelectedEntity] = useState<any | null>(null);
  const [projectStats, setProjectStats] = useState<Record<number, any>>({});
  const [backendStatus, setBackendStatus] = useState('connecting'); // 'connected' | 'error' | 'connecting'



  const chatEndRef = useRef(null);
  const ignoreUrlSyncRef = useRef(false);
  // handleSessionSelect is defined much further down (closes over a lot of
  // component state) but is needed by the URL-sync effect above its own
  // declaration — kept fresh via ref/effect rather than moved, same "latest
  // ref" pattern as projectsRef/selectedProjectRef below.
  const handleSessionSelectRef = useRef<(session: any) => void>(() => {});
  // Guards the debounced snapshot auto-save from firing while handleSessionSelect
  // is itself applying a restored snapshot (would otherwise immediately re-save it).
  const isRestoringSnapshotRef = useRef(false);
  const snapshotDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [pinnedCode, setPinnedCode] = useState<{
    filepath: string;
    line: number;
    label?: string;
    context?: string;
    sourceId?: number | string | null;
    program?: string | null;
    section?: string | null;
    paragraph?: string | null;
  } | null>(null);

  const [panelFrozen, setPanelFrozen] = useState<boolean[]>([false]);
  const [collapsedPanels, setCollapsedPanels] = useState<boolean[]>([false]);
  // Zuletzt fokussiertes Objekt je Panel — wird in der Fokusleiste des Panels
  // angezeigt, getrennt von panelSelections, weil es keine Datei/Doc/Entity ist.
  // Wird in AP-5 zum Fokus-Objekt nach F-067 ausgebaut.
  const [panelFocusObject, setPanelFocusObject] = useState<Array<any | null>>([null]);
  const [panelSelections, setPanelSelections] = useState<Array<{
    selectedFile: string | null;
    selectedDoc: any | null;
    selectedEntity: any | null;
    selectedLine: number | null;
  }>>([
    { selectedFile: null, selectedDoc: null, selectedEntity: null, selectedLine: null },
  ]);

  // Synchronize unfrozen panels with global state — but only panels for which the
  // new selection actually makes sense. Chat and the two graph views (knowledge
  // graph, call graph) mirror every focus change unconditionally (chat wants the
  // context, and every selectable object should have a node in both graphs);
  // code/doc/webview panels only follow selections of their own kind, otherwise
  // e.g. clicking a document would make an open Doku panel try to load it as a
  // document.
  // Done during render (guarded by a combined-deps state comparison) rather
  // than in an effect.
  const [prevPanelSyncDeps, setPrevPanelSyncDeps] = useState({ selectedFile, selectedDoc, selectedEntity, selectedLine, panelFrozen, panelConfigs });
  if (
    prevPanelSyncDeps.selectedFile !== selectedFile ||
    prevPanelSyncDeps.selectedDoc !== selectedDoc ||
    prevPanelSyncDeps.selectedEntity !== selectedEntity ||
    prevPanelSyncDeps.selectedLine !== selectedLine ||
    prevPanelSyncDeps.panelFrozen !== panelFrozen ||
    prevPanelSyncDeps.panelConfigs !== panelConfigs
  ) {
    setPrevPanelSyncDeps({ selectedFile, selectedDoc, selectedEntity, selectedLine, panelFrozen, panelConfigs });
    const incomingType = getSelectionViewType(selectedFile, selectedDoc);
    setPanelSelections(prev => {
      let changed = false;
      const next = prev.map((sel, idx) => {
        if (panelFrozen[idx]) return sel;
        const panelType = panelConfigs[idx];
        const shouldSync = panelType === 'chat' || panelType === 'graph' || panelType === 'callgraph'
          || incomingType === null || incomingType === panelType;
        if (!shouldSync) return sel;
        if (
          sel.selectedFile !== selectedFile ||
          sel.selectedDoc !== selectedDoc ||
          sel.selectedEntity !== selectedEntity ||
          sel.selectedLine !== selectedLine
        ) {
          changed = true;
          return {
            selectedFile,
            selectedDoc,
            selectedEntity,
            selectedLine
          };
        }
        return sel;
      });
      return changed ? next : prev;
    });
  }

  const togglePanelFreeze = (index: number) => {
    setPanelFrozen(prev => {
      const next = [...prev];
      next[index] = !next[index];

      // Catch up on unfreeze
      if (!next[index]) {
        setPanelSelections(prevSels => {
          const nextSels = [...prevSels];
          nextSels[index] = {
            selectedFile,
            selectedDoc,
            selectedEntity,
            selectedLine: null
          };
          return nextSels;
        });
      }
      return next;
    });
  };

  const togglePanelCollapse = (index: number) => {
    setCollapsedPanels(prev => {
      const next = [...prev];
      next[index] = !next[index];
      return next;
    });
  };

  const addPanel = (type: string, selectionOverride?: {
    selectedFile?: string | null;
    selectedDoc?: any | null;
    selectedEntity?: any | null;
  }, frozenOverride?: boolean) => {
    if (panelConfigs.length >= 4) return;
    setPanelFrozen(prev => [...prev, frozenOverride ?? false]);
    setCollapsedPanels(prev => [...prev, false]);
    setPanelFocusObject(prev => [...prev, null]);
    setPanelSelections(prev => [...prev, {
      selectedFile: selectionOverride ? (selectionOverride.selectedFile ?? null) : selectedFile,
      selectedDoc: selectionOverride ? (selectionOverride.selectedDoc ?? null) : selectedDoc,
      selectedEntity: selectionOverride ? (selectionOverride.selectedEntity ?? null) : selectedEntity,
      selectedLine: null
    }]);
    setPanelConfigs(prev => [...prev, type]);
  };

  // Opens a view only if it isn't already open — this is how views come into
  // existence "on demand" (file/doc/entity selected, graph icon clicked, ...)
  // instead of all being visible from the start.
  //
  // `pendingPanelTypesRef` guards against a same-tick double-add: some call
  // sites (e.g. the graph's "open in view" button) fire two handlers back to
  // back that both call ensurePanelType for the same type (one for the
  // generic selection, one for the doc-specific focus request) before
  // React has re-rendered with the first addPanel's result — without this,
  // both read the same stale `panelConfigs` snapshot, see the type missing,
  // and each add a panel, opening the same document/model twice.
  const pendingPanelTypesRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    pendingPanelTypesRef.current.clear();
  }, [panelConfigs]);

  const ensurePanelType = (type: string, selectionOverride?: {
    selectedFile?: string | null;
    selectedDoc?: any | null;
    selectedEntity?: any | null;
  }, frozenOverride?: boolean) => {
    if (panelConfigs.includes(type) || pendingPanelTypesRef.current.has(type)) return;
    pendingPanelTypesRef.current.add(type);
    addPanel(type, selectionOverride, frozenOverride);
  };

  // Collapsed chat panels shrink to a narrow rail; siblings reclaim the space
  const isPanelCollapsed = (index: number) =>
    collapsedPanels[index] && panelConfigs[index] === 'chat';
  const cellCls = (index: number, expanded: string) =>
    cn("h-full min-w-0", isPanelCollapsed(index) ? "flex-none w-12" : expanded);

  // Pin whatever the user just focused (a file, a document, a code entity) into the
  // chat so it's ready as context the moment they start typing — same idea as the
  // Pin unten, verallgemeinert auf jeden Objekttyp.
  const pinFileFocus = (path: string | null, line: number | null = null) => {
    if (!path) return;
    setPinnedCode({ filepath: path, line: line || 0 });
  };
  const pinEntityFocus = (ent: any) => {
    if (!ent) return;
    setPinnedCode({ filepath: ent.file_path, line: ent.start_line, label: ent.name });
  };

  // Pin a focused object into the chat so the LLM can build context on it,
  // and remember it for that panel's focus bar
  const handleObjectFocus = (obj: any, panelIndex: number) => {
    if (!obj) return;
    setPanelFocusObject(prev => {
      const next = [...prev];
      next[panelIndex] = obj;
      return next;
    });
    const sel = panelSelections[panelIndex];
    const filepath = sel?.selectedFile || sel?.selectedDoc?.name || t('page.objectFileFallback');
    const context =
      `${t('page.focusedObjectLabel')}: ${obj.name}\n` +
      `Typ: ${obj.type}\n` +
      `Material: ${obj.material}\n` +
      `Volumen: ${obj.volume}\n` +
      `Feuerwiderstand: ${obj.fireRating}`;
    setPinnedCode({ filepath, line: 0, label: obj.name, context });
    const textarea = document.getElementById("chat-textarea") as HTMLTextAreaElement;
    if (textarea) textarea.focus();
  };

  const handlePanelFileSelect = async (index: number, path: string | null, line: number | null = null, sourceId: number | string | null = null, openIfMissing: boolean = true) => {
    pinFileFocus(path, line);
    const { isDoc, isWebOrigin, resolvedSourceId } = resolveReferenceTarget(path, sourceId, connectedSources);
    const targetDoc = resolvedSourceId && (isDoc || isWebOrigin)
      ? { id: resolvedSourceId, name: path, ...(isWebOrigin ? { isWebOrigin: true, url: path } : {}) }
      : null;
    const targetType = getSelectionViewType(path, targetDoc);
    let focusedEntity = path && !targetDoc
      ? projectEntities.find((ent: any) =>
          ent.file_path === path &&
          (!resolvedSourceId || Number(ent.source_id) === Number(resolvedSourceId)) &&
          (ent.type === 'program' || ent.type === 'copybook')) || null
      : null;
    if (path && resolvedSourceId && !isWebOrigin) {
      try {
        focusedEntity = (await api.resolveEntity(Number(resolvedSourceId), path, selectedProject?.id)).data;
      } catch (error: any) {
        // A plain text file legitimately has no COBOL entity. Authentication and
        // server errors still surface in the console/global 401 handler.
        if (error?.response?.status !== 404) console.error('Failed to resolve code focus:', error);
      }
    }

    // A reference can point at a different kind of view than the panel it was
    // clicked from (e.g. a doc source cited from a chat panel) — route it to
    // an already-open panel of that type, or open one, instead of only updating
    // state that this panel's own view never reads.
    // `openIfMissing=false` (a plain Graph View node click, as opposed to its
    // "open in matching view" button) must not surface a panel on its own — it
    // only nudges an already-open, unfrozen ("live") panel of the matching type.
    let targetIndex = index;
    if (targetType && targetType !== panelConfigs[index]) {
      const existingIndex = panelConfigs.indexOf(targetType);
      if (existingIndex === -1) {
        if (!openIfMissing) return;
        ensurePanelType(targetType, { selectedFile: path, selectedDoc: targetDoc, selectedEntity: null });
      } else {
        targetIndex = existingIndex;
        if (!openIfMissing && panelFrozen[targetIndex]) return;
      }
      // On mobile only one panel is visible at a time (see activeMobileTab render
      // switch below) — surface the panel the reference just opened/targeted.
      setActiveMobileTab(targetType === 'graph' ? 'graph' : targetType === 'chat' ? 'chat' : 'editor');
    }

    if (panelFrozen[targetIndex]) {
      setPanelSelections(prev => {
        const next = [...prev];
        next[targetIndex] = {
          selectedFile: path,
          selectedDoc: targetDoc,
          selectedEntity: focusedEntity,
          selectedLine: line
        };
        return next;
      });
    } else {
      setSelectedDoc(targetDoc);
      setSelectedFile(targetDoc ? null : path);
      setSelectedEntity(focusedEntity);
      setSelectedLine(targetDoc ? null : line);
      setPanelSelections(prev => {
        const next = [...prev];
        next[targetIndex] = {
          ...next[targetIndex],
          selectedEntity: focusedEntity,
          selectedLine: line
        };
        return next;
      });
    }
  };

  // "Open in view" from the Knowledge Graph on a plain document/PDF node. Needed because a graph
  // panel is pinned to contentType 'graph' (see the SplitPaneWorkspace render
  // below), so selecting a document there only updates shared selection state
  // and never surfaces a document panel on its own; this opens/navigates one.
  //
  // Always updates the global selection (not just when a 'doc' panel already
  // existed) — the graph panel is opened frozen (see handleOpenGraphView), so
  // its own clicks never touch global selectedFile/selectedDoc. Leaving global
  // state stale here would make the sync effect above see incomingType===null
  // on its next run (panelConfigs/panelFrozen changing is itself a dependency)
  // and blank out the doc panel we just seeded via ensurePanelType.
  const handleDocFocusRequest = (filePath: string, sourceId: number | string | null, openIfMissing: boolean = true) => {
    if (!sourceId) return;
    if (!panelConfigs.includes('doc') && !openIfMissing) return;
    const selectionOverride = {
      selectedFile: null,
      selectedDoc: { id: sourceId, name: filePath },
      selectedEntity: null,
    };
    ensurePanelType('doc', selectionOverride);
    setSelectedDoc({ id: sourceId, name: filePath });
    setSelectedFile(null);
    setSelectedLine(null);
  };

  const handlePanelEntitySelect = async (index: number, ent: any) => {
    pinEntityFocus(ent);
    setPanelSelections(prev => {
      const next = [...prev];
      next[index] = { ...next[index], selectedEntity: ent };
      return next;
    });
    if (!panelFrozen[index]) {
      setSelectedEntity(ent);
      // Hält den Referenzen-Badge (fileReferences.length) synchron mit dem im
      // Code-Viewer angeklickten Objekt — ohne diesen Aufruf bleibt die Zahl auf
      // dem Stand der zuletzt per handleFileSelect/handleEntitySelect geladenen
      // Datei bzw. Entity stehen.
      loadFileReferences(ent.file_path, ent.name);
    }
  };

  // Content-/Navigationsstate der "Situation" für den Chat-Snapshot — bewusst ohne
  // reine UI-Prefs (Theme, Editor-Font, Sidebar-/Panel-Collapse). panelFrozen ist
  // enthalten, obwohl es wie ein UI-Toggle wirkt: es entscheidet, ob ein Panel an
  // seine eigene Datei/Doc/Entity gebunden ist statt den globalen Fokus zu spiegeln
  // (s. Sync-Effekt oben) — ohne es würden beim Restore mehrere Panels auf dieselbe
  // Auswahl kollabieren.
  const buildWorkspaceSnapshot = () => ({
    panelConfigs,
    panelSelections,
    panelFocusObject,
    panelFrozen,
    activeRightTab,
    splitPercent,
    fileNavStack,
    pinnedCode,
    selectedProjectId: selectedProject?.id ?? null,
    selectedSourceId: selectedSource?.id ?? null,
  });

  // Automatisches, debounced Speichern des Workspace-Snapshots je aktiver Session.
  useEffect(() => {
    if (!activeSessionId || isRestoringSnapshotRef.current) return;
    if (snapshotDebounceRef.current) clearTimeout(snapshotDebounceRef.current);
    snapshotDebounceRef.current = setTimeout(() => {
      api.updateChatSessionSnapshot(activeSessionId, buildWorkspaceSnapshot())
        .catch(err => console.error("Failed to save workspace snapshot", err));
    }, 1200);
    return () => {
      if (snapshotDebounceRef.current) clearTimeout(snapshotDebounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSessionId, panelConfigs, panelSelections, panelFocusObject, panelFrozen, activeRightTab, splitPercent, fileNavStack, pinnedCode, selectedProject, selectedSource]);

  const router = useRouter();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const chatUuidParam = searchParams.get('chat');

  const [selectedSourceRepoId, setSelectedSourceRepoId] = useState<string>("all");
  const [fileReferences, setFileReferences] = useState<any[]>([]);
  const [isLoadingReferences, setIsLoadingReferences] = useState(false);
  const [isReferencesDropdownOpen, setIsReferencesDropdownOpen] = useState(false);
  const [referencesTab, setReferencesTab] = useState<'code' | 'docs'>('code');
  const [activeSourceType, setActiveSourceType] = useState<string | null>(null);
  const [connectedSources, setConnectedSources] = useState<any[]>([
    { id: 'conf-init', type: 'Confluence', name: 'Firmen-Wiki', repoId: 'all', spaces: ['ENG', 'PROD'] }
  ]);
  const [pinnedSourceIds, setPinnedSourceIds] = useState<number[]>([]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('pinnedSourceIds');
      if (saved) {
        try {
          (() => setPinnedSourceIds(JSON.parse(saved)))();
        } catch (e) {
          console.error(e);
        }
      }
    }
  }, []);

  const togglePinSource = (sourceId: number) => {
    setPinnedSourceIds(prev => {
      let next = [...prev];
      if (next.includes(sourceId)) {
        next = next.filter(id => id !== sourceId);
      } else {
        if (next.length >= 4) {
          showToast(t('settings.sourcesTab.maxPinsReached'), 'error');
          return prev;
        }
        next.push(sourceId);
      }
      localStorage.setItem('pinnedSourceIds', JSON.stringify(next));
      return next;
    });
  };

  const editorRef = useRef<any>(null);

  // Reset activeMobileTab to 'chat' if no file or document is selected and we
  // are not in graph mode. Done during render (guarded by state comparisons)
  // rather than in an effect, since activeMobileTab is otherwise user-controlled.
  const [prevMobileTabResetDeps, setPrevMobileTabResetDeps] = useState({ selectedFile, selectedDoc, activeRightTab });
  if (
    prevMobileTabResetDeps.selectedFile !== selectedFile ||
    prevMobileTabResetDeps.selectedDoc !== selectedDoc ||
    prevMobileTabResetDeps.activeRightTab !== activeRightTab
  ) {
    setPrevMobileTabResetDeps({ selectedFile, selectedDoc, activeRightTab });
    if (!selectedFile && !selectedDoc && activeRightTab !== 'graph') {
      setActiveMobileTab('chat');
    }
  }

  // Sync activeMobileTab with activeRightTab when switching to graph on mobile
  const [prevGraphTabSyncDeps, setPrevGraphTabSyncDeps] = useState({ activeRightTab, isMobile });
  if (prevGraphTabSyncDeps.activeRightTab !== activeRightTab || prevGraphTabSyncDeps.isMobile !== isMobile) {
    setPrevGraphTabSyncDeps({ activeRightTab, isMobile });
    if (activeRightTab === 'graph' && isMobile) {
      setActiveMobileTab('graph');
    }
  }

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 6000);
  };

  // Initial connection check, repositories load & settings restoration
  useEffect(() => {
    // Monaco's harmless "Canceled" error is already suppressed globally by the
    // capture-phase <script> in app/layout.tsx, which runs in <head> before
    // this component ever mounts — a second copy of the same listeners here
    // was dead weight (layout's stopImmediatePropagation() fires first).
    (() => {

    // 1. Restore Theme from LocalStorage
    const savedTheme = localStorage.getItem('doctus-theme');
    if (savedTheme === 'light' || savedTheme === 'dark') {
      setTheme(savedTheme);
    }

    const savedProfilesStr = localStorage.getItem('doctus-llm-profiles');
    let profilesList: any[] = [];
    if (savedProfilesStr) {
      try {
        profilesList = JSON.parse(savedProfilesStr);
      } catch (e) {
        console.error(e);
      }
    }

    if (profilesList.length === 0) {
      const legacyProvider = localStorage.getItem('doctus-llm-provider') || 'ollama';
      const legacyModel = localStorage.getItem('doctus-llm-model') || "qwen2.5:1.5b";
      const legacyApiKey = localStorage.getItem('doctus-llm-api-key') || '';
      const legacyBaseUrl = localStorage.getItem('doctus-llm-base-url') || '';

      profilesList = [
        {
          id: "ollama-default",
          name: t('page.defaultLlmProfiles.localOllama'),
          provider: "ollama",
          model: legacyProvider === 'ollama' ? legacyModel : "qwen2.5:1.5b"
        }
      ];

      if (legacyProvider !== 'ollama' || (legacyProvider === 'ollama' && legacyModel !== 'qwen2.5:1.5b')) {
        profilesList.push({
          id: "custom-legacy",
          name: legacyProvider === 'openai' ? t('page.defaultLlmProfiles.companyGpt') : t('page.defaultLlmProfiles.providerModel', { provider: legacyProvider.toUpperCase() }),
          provider: legacyProvider,
          model: legacyModel,
          apiKey: legacyApiKey,
          baseUrl: legacyBaseUrl
        });
      }
      localStorage.setItem('doctus-llm-profiles', JSON.stringify(profilesList));
    }

    setLlmProfiles(profilesList);

    const savedActiveId = localStorage.getItem('doctus-active-profile-id');
    if (savedActiveId && profilesList.some(p => p.id === savedActiveId)) {
      setActiveProfileId(savedActiveId);

      // Restore AI Parameters from active profile
      const activeProfile = profilesList.find(p => p.id === savedActiveId);
      if (activeProfile) {
        if (activeProfile.temperature !== undefined) setTemperature(activeProfile.temperature);
        if (activeProfile.systemPrompt !== undefined) setSystemPrompt(activeProfile.systemPrompt);
      }
    } else {
      const initialId = profilesList[0]?.id || "ollama-default";
      setActiveProfileId(initialId);
      localStorage.setItem('doctus-active-profile-id', initialId);

      // Restore from the first profile if no active one was saved
      const firstProfile = profilesList[0];
      if (firstProfile) {
        if (firstProfile.temperature !== undefined) setTemperature(firstProfile.temperature);
        if (firstProfile.systemPrompt !== undefined) setSystemPrompt(firstProfile.systemPrompt);
      }
    }

    })();
    // Intentionally mount-once: only reads/writes localStorage-backed profile
    // state. Including `t` would re-run the whole restore (and, for users on
    // first run with no saved profiles yet, rebuild the default profile names)
    // on every language switch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Backend-Daten erst nach bestätigter Session laden (getMe erfolgreich). Vorher
  // feuerten /projects, /knowledge-sources, /chat/sessions ungegatet beim Mount mit
  // und lieferten auf der Login-Seite unnötige 401er (Konsolen-Rauschen + Last durch
  // unauthentifizierte Clients) — bis zum Login zeigt die App ohnehin nur die LoginView.
  useEffect(() => {
    if (!isLoggedIn) return;

    (() => setBackendStatus('connecting'))();

    // 2. Fetch All Initial Data from Backend
    api.getProjects()
      .then(res => {
        setProjects(res.data);
        setBackendStatus('connected');
      })
      .catch(err => {
        console.error(err);
        setBackendStatus('error');
        showToast(t('page.toast.backendConnectionFailed'), "error");
      });

    // Fetch Knowledge Sources (e.g. Confluence, Local Docs)
    api.getKnowledgeSources()
      .then(res => {
        setConnectedSources(res.data);
        // pinnedSourceIds is persisted client-side in localStorage and can
        // go stale (source deleted, or the whole demo/DB reseeded) — prune
        // any pinned id that no longer matches a real source so it stops
        // silently eating into the pin limit.
        setPinnedSourceIds(prev => {
          const valid = prev.filter(id => res.data.some((s: any) => s.id === id));
          if (valid.length !== prev.length) {
            localStorage.setItem('pinnedSourceIds', JSON.stringify(valid));
          }
          return valid;
        });
      })
      .catch(err => {
        console.error("Failed to load knowledge sources", err);
      });

    // Fetch AI Model Configuration
    api.getModelInfo()
      .then(res => {
        if (res.data.llm) setActiveLlmModel(res.data.llm);
        if (res.data.embedding) setActiveEmbeddingModel(res.data.embedding);
      })
      .catch(err => {
        console.error("Failed to load model info", err);
      });

    // Fetch Available Models from Ollama
    api.getModels()
      .then(res => {
        if (res.data.models) {
          setAvailableModels(res.data.models);
        }
      })
      .catch(err => {
        console.error("Failed to load available models", err);
      });

    // Fetch Past Chat Sessions
    api.getChatSessions()
      .then(res => {
        setSessions(res.data);
        setIsSessionsLoaded(true);
      })
      .catch(err => {
        console.error("Failed to load chat sessions", err);
        setIsSessionsLoaded(true);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoggedIn]);

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
  }, [chatUuidParam, sessions, activeSessionId, isSessionsLoaded, pathname, router, t]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  // Tracks in-flight/fetched project ids instead of reading projectStats
  // itself, so this effect doesn't need projectStats as a dependency (that
  // would make it re-run every time a fetch below completes).
  const fetchedProjectStatsIdsRef = useRef<Set<number>>(new Set());
  useEffect(() => {
    if (isSettingsOpen && projects.length > 0) {
      projects.forEach(project => {
        if (!fetchedProjectStatsIdsRef.current.has(project.id)) {
          fetchedProjectStatsIdsRef.current.add(project.id);
          api.getProjectStats(project.id)
            .then(res => {
              setProjectStats(prev => ({ ...prev, [project.id]: res.data }));
            })
            .catch(err => {
              console.error(`Error fetching stats for project ${project.id}:`, err);
              fetchedProjectStatsIdsRef.current.delete(project.id);
            });
        }
      });
    }
  }, [isSettingsOpen, projects]);

  // Refs to hold latest state for the polling interval callback
  const projectsRef = useRef(projects);
  const selectedProjectRef = useRef(selectedProject);
  useEffect(() => { projectsRef.current = projects; }, [projects]);
  useEffect(() => { selectedProjectRef.current = selectedProject; }, [selectedProject]);

  // Sync workspaceSplit preset → splitPercent. Done during render (guarded by
  // a state comparison) rather than in an effect, since splitPercent is
  // otherwise user-controlled (dragging the divider).
  const [prevWorkspaceSplitForSync, setPrevWorkspaceSplitForSync] = useState(workspaceSplit);
  if (workspaceSplit !== prevWorkspaceSplitForSync) {
    setPrevWorkspaceSplitForSync(workspaceSplit);
    const map: Record<string, number> = { '50/50': 50, '40/60': 40, '60/40': 60, '45/55': 45 };
    setSplitPercent(map[workspaceSplit] ?? 45);
  }

  // Drag-to-resize: global mouse listeners
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDraggingRef.current || !splitContainerRef.current) return;
      const containerWidth = splitContainerRef.current.getBoundingClientRect().width;
      const deltaX = e.clientX - dragStartXRef.current;
      const deltaPercent = (deltaX / containerWidth) * 100;
      const newPercent = Math.max(20, Math.min(80, dragStartPercentRef.current + deltaPercent));
      setSplitPercent(newPercent);
    };
    const handleMouseUp = () => {
      if (!isDraggingRef.current) return;
      isDraggingRef.current = false;
      setIsDragging(false);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  // Poll project status if any are parsing or pending
  const hasActiveTask = projects.some((p: any) => p.status === 'parsing' || p.status === 'pending');
  useEffect(() => {
    if (!hasActiveTask) return;

    const interval = setInterval(async () => {
      try {
        const res = await api.getProjects();
        const updatedProjects = res.data;
        const currentProjects = projectsRef.current;
        const currentSelectedProject = selectedProjectRef.current;

        // Check if any project transitioned to completed or error to notify user
        currentProjects.forEach((oldProject: any) => {
          const newProject = updatedProjects.find((p: any) => p.id === oldProject.id);
          if (newProject && oldProject.status !== newProject.status) {
            if (newProject.status === 'completed') {
              showToast(t('page.toast.projectAnalyzed', { name: newProject.name }), 'success');

              // Trigger re-fetch of stats for this project to show language breakdown immediately
              api.getProjectStats(newProject.id)
                .then(statRes => {
                  setProjectStats(prev => ({ ...prev, [newProject.id]: statRes.data }));
                })
                .catch(err => console.error(`Error fetching stats for completed project ${newProject.id}:`, err));

              if (currentSelectedProject && currentSelectedProject.id === newProject.id) {
                setSelectedProject(newProject);
                api.getProjectFiles(newProject.id).then(fileRes => setFiles(fileRes.data)).catch(console.error);
                api.getProjectEntities(newProject.id).then(entRes => setProjectEntities(entRes.data)).catch(console.error);
              }
            } else if (newProject.status === 'error') {
              showToast(t('page.toast.projectAnalysisError', { name: newProject.name }), 'error');
            }
          }
        });

        setProjects(updatedProjects);
      } catch (err) {
        console.error("Error polling project status:", err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [hasActiveTask, t]);

  // Load project entities when selected project changes
  useEffect(() => {
    if (!selectedProject) {
      (() => setProjectEntities([]))();
      return;
    }
    const fetchEntities = async () => {
      try {
        const res = await api.getProjectEntities(selectedProject.id);
        setProjectEntities(res.data);
      } catch (err) {
        console.error("Fehler beim Laden der Code-Objekte:", err);
      }
    };
    fetchEntities();
  }, [selectedProject]);

  // Resets just the chat/session identity — used internally whenever the app
  // auto-starts a fresh conversation as a side effect of something else (switching
  // project/file mid-chat, removing the active session, opening the graph view),
  // where the caller deliberately keeps its own view/panel state around afterward.
  const resetChatSession = () => {
    ignoreUrlSyncRef.current = true;
    setChatMessages([]);
    setSelectedFile(null);
    setIsEditorMaximized(false);
    setActiveSessionId(null);

    // Clear URL chat parameter
    router.push(pathname);

    showToast(t('page.toast.newChatStarted'), "success");
  };

  // "+ Neuer Chat": resets the conversation/views to a clean slate, but
  // deliberately keeps the current project focus (selectedProject/files/
  // projectEntities) — the button starts a fresh chat *within* the current
  // project, it does not back out to "no project selected". Every other
  // open view/panel, file focus, and modal closes, not just the message
  // list (they otherwise stay open and keep adapting to whatever file was
  // previously focused).
  const startNewChat = () => {
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
    setPanelFrozen([false]);
    setCollapsedPanels([false]);
    setPanelFocusObject([null]);
    setSplitPercent(45);
    setWorkspaceSplit("45/55");
    setIsSettingsOpen(false);
  };

  const handleProjectSelect = async (project) => {
    if (!project) {
      setSelectedProject(null);
      setFiles([]);
      setProjectEntities([]);

      const activeSession = sessions.find(s => s.id === activeSessionId);
      if (activeSessionId && activeSession && activeSession.project_id !== null) {
        resetChatSession();
      }
      showToast(t('page.toast.projectSelectedGeneral') || "Allgemeiner Kontext ausgewählt", "success");
      return;
    }
    // status/url are only populated when a git repo is attached (see serialize_project) —
    // a git-free project has status=null and must stay selectable.
    if (project.url && project.status !== 'completed') {
      showToast(t('page.toast.projectStillAnalyzing', { name: project.name }), 'warning');
      return;
    }
    setSelectedProject(project);
    setBranch(project.branch || "main");

    const activeSession = sessions.find(s => s.id === activeSessionId);
    if (activeSessionId && activeSession && activeSession.project_id !== project.id) {
      resetChatSession();
    }

    try {
      const res = await api.getProjectFiles(project.id);
      setFiles(res.data);
      showToast(t('page.toast.projectSelected', { name: project.name }), "success");
    } catch (err) {
      showToast(t('page.toast.filesFetchFailed'), "error");
    }
  };

  const loadFileReferences = async (filePath, entityName = null, projectOverride = null) => {
    const project = projectOverride || selectedProject;
    if (!project) return;
    setIsLoadingReferences(true);
    try {
      const res = await api.getProjectReferences(project.id, filePath, entityName || undefined);
      setFileReferences(res.data);
    } catch (err) {
      console.error("Fehler beim Laden der Referenzen:", err);
      setFileReferences([]);
    } finally {
      setIsLoadingReferences(false);
    }
  };

  const handleFileSelect = async (path, line = null, sourceId = null, projectOverride = null) => {
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
  };

  const handleGutterClick = (panelIndex: number, lineNumber: number, lineContent: string) => {
    const selection = panelSelections[panelIndex];
    const filepath = selection?.selectedFile;
    if (!filepath) return;

    const enclosingEntities = projectEntities.filter((candidate: any) =>
      candidate.file_path === filepath &&
      candidate.start_line <= lineNumber &&
      candidate.end_line >= lineNumber
    );
    const entity = selection?.selectedEntity || enclosingEntities[0];
    const enclosingName = (type: string) => enclosingEntities
      .filter((candidate: any) => candidate.type === type)
      .sort((a: any, b: any) => (a.end_line - a.start_line) - (b.end_line - b.start_line))[0]?.name || null;
    setPinnedCode({
      filepath,
      line: lineNumber,
      label: `${filepath.split('/').pop()}:${lineNumber}`,
      context: lineContent,
      sourceId: entity?.source_id || selectedSource?.id || null,
      program: enclosingName('program'),
      section: enclosingName('section'),
      paragraph: enclosingName('paragraph')
    });
    ensurePanelType('chat');
    setActiveMobileTab('chat');
    setTimeout(() => {
      const textarea = document.getElementById("chat-textarea") as HTMLTextAreaElement;
      if (textarea) {
        textarea.focus();
      }
    }, 150);
  };

  // Counterpart to handleGutterClick for the gutter menu's "Etwas zu X fragen"
  // option — pins the enclosing code object (not just the clicked line) as
  // chat context. The entity is resolved by SplitPaneWorkspace itself (it
  // already has the smallest enclosing entity for the clicked line at hand).
  const handleGutterAskEntity = (panelIndex: number, entity: any) => {
    if (!entity) return;
    setPinnedCode({
      filepath: entity.file_path,
      line: entity.start_line,
      label: entity.name,
      sourceId: entity.source_id || selectedSource?.id || null,
    });
    ensurePanelType('chat');
    setActiveMobileTab('chat');
    setTimeout(() => {
      const textarea = document.getElementById("chat-textarea") as HTMLTextAreaElement;
      if (textarea) {
        textarea.focus();
      }
    }, 150);
  };

  const handleEntitySelect = async (ent: any, projectOverride: any = null) => {
    setSelectedEntity(ent);
    pinEntityFocus(ent);
    loadFileReferences(ent.file_path, ent.name, projectOverride);

    await handleFileSelect(ent.file_path, ent.start_line, ent.source_id ?? null, projectOverride);
  };

  const handleNavigateBack = async () => {
    if (fileNavStack.length === 0) return;
    const newStack = fileNavStack.slice(0, -1);
    const prev = fileNavStack[fileNavStack.length - 1];
    setFileNavStack(newStack);
    if (newStack.length === 0) {
      setIsEditorMaximized(false);
    }
    isEditorNavigatingRef.current = true;
    if (prev.file) {
      await handleFileSelect(prev.file, null, null);
    } else if (prev.doc) {
      await handleFileSelect(prev.doc.name, null, prev.doc.id);
    }
  };

  const handleSearchResultSelect = async (result: any) => {
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
      pinFileFocus(filePath);
      await handleFileSelect(filePath, null, meta.source_id, targetProject);
    } else if (result.node_type === 'knowledge_source') {
      setSelectedSource({ id: result.node_id, name: result.node_label, project_id: meta.project_id, type: meta.type });
      showToast(t('page.toast.sourceFocused', { name: result.node_label }), "success");
    }
  };

  // Shared SSE-consumer for both a fresh send and a retry/regenerate — both stream
  // into a specific `chatMessages` slot (`targetIndex`), they only differ in what
  // that slot was initialized to and what request body they send.
  const runChatStream = async (requestBody: any, targetIndex: number) => {
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) {
        throw new Error(t('page.error.httpError', { status: response.status }));
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) {
        throw new Error(t('page.error.streamReaderInit'));
      }

      let buffer = "";
      let accumulatedSteps: any[] = [];
      let currentThought = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        let boundary = buffer.indexOf('\n\n');

        while (boundary !== -1) {
          const message = buffer.substring(0, boundary).trim();
          buffer = buffer.substring(boundary + 2);

          if (message.startsWith('data: ')) {
            const jsonStr = message.substring(6);
            try {
              const data = JSON.parse(jsonStr);

              if (data.type === 'session') {
                const newSessionId = data.session_id;
                const newSessionUuid = data.session_uuid;

                if (!activeSessionId && newSessionId) {
                  ignoreUrlSyncRef.current = true;
                  setActiveSessionId(newSessionId);
                  const newSession = {
                    id: newSessionId,
                    uuid: newSessionUuid,
                    title: data.session_title || (requestBody.message.length > 28 ? requestBody.message.substring(0, 25) + "..." : requestBody.message),
                    project_id: selectedProject?.id,  // Must match backend's _serialize_session shape
                    project: selectedProject,
                    source_id: selectedSource?.id || null,
                    source: selectedSource
                  };
                  setSessions(prev => [newSession, ...prev]);

                  if (newSessionUuid) {
                    const params = new URLSearchParams(window.location.search);
                    params.set('chat', newSessionUuid);
                    router.push(`${pathname}?${params.toString()}`);
                  }
                }
              } else if (data.type === 'sources') {
                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = { ...target, sources: data.sources };
                  }
                  return next;
                });
              } else if (data.type === 'content_chunk') {
                currentThought += data.content;
                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = { ...target, content: target.content + data.content };
                  }
                  return next;
                });
              } else if (data.type === 'tool_call') {
                const newSteps = [...accumulatedSteps];
                if (currentThought.trim()) {
                  newSteps.push({ type: 'thought', content: currentThought });
                  currentThought = "";
                }
                newSteps.push({
                  type: 'tool_call',
                  name: data.name,
                  arguments: data.arguments,
                  id: data.id
                });
                accumulatedSteps = newSteps;

                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = {
                      ...target,
                      content: "",
                      metadata: {
                        ...target.metadata,
                        agent_steps: accumulatedSteps
                      }
                    };
                  }
                  return next;
                });
              } else if (data.type === 'tool_result') {
                const newSteps = [...accumulatedSteps];
                newSteps.push({
                  type: 'tool_result',
                  name: data.name,
                  result: data.result,
                  id: data.id
                });
                accumulatedSteps = newSteps;

                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = {
                      ...target,
                      metadata: {
                        ...target.metadata,
                        agent_steps: accumulatedSteps
                      }
                    };
                  }
                  return next;
                });
              } else if (data.type === 'turn_completed') {
                if (data.has_tool_calls) {
                  currentThought = "";
                }
              } else if (data.type === 'answer') {
                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = {
                      ...target,
                      content: data.content,
                      metadata: {
                        ...target.metadata,
                        agent_steps: data.agent_steps || accumulatedSteps
                      }
                    };
                  }
                  return next;
                });
              } else if (data.type === 'message_saved') {
                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = { ...target, id: data.message_id };
                  }
                  return next;
                });
              } else if (data.type === 'error') {
                const errMsgText = t('page.error.chatFetchFailedWithMessage', { message: data.error });
                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = { ...target, content: errMsgText };
                  }
                  return next;
                });
                showToast(t('page.toast.aiQueryFailed'), "error");
                return;
              }

            } catch (e) {
              console.error("Failed to process stream chunk", e, jsonStr);
            }
          }
          boundary = buffer.indexOf('\n\n');
        }
      }
    } catch (error: any) {
      console.error(error);
      let errMsgText = t('page.error.chatFetchFailed');
      if (error?.message) {
        errMsgText = t('page.error.chatFetchFailedWithMessage', { message: error.message });
      }
      setChatMessages(prev => {
        const next = [...prev];
        const target = next[targetIndex];
        if (target && target.role === 'assistant') {
          next[targetIndex] = { ...target, content: errMsgText };
        }
        return next;
      });
      showToast(t('page.toast.aiQueryFailed'), "error");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendChat = async (overrideMsg?: string, extraMetadata?: Record<string, any>) => {
    const msgToSend = (overrideMsg || currentMessage).trim();
    if (!msgToSend || isLoading) return;

    const userMsgContent = msgToSend;
    const newUserMsg = {
      role: 'user',
      content: userMsgContent,
      metadata: {
        project: selectedProject ? { name: selectedProject.name, id: selectedProject.id } : null,
        source: selectedSource ? { name: selectedSource.name, id: selectedSource.id } : null,
        pinned: pinnedCode ? {
          filepath: pinnedCode.filepath,
          line: pinnedCode.line,
          label: pinnedCode.label,
          source_id: pinnedCode.sourceId || null
        } : null,
        refs: pinnedCode?.line ? [{
          file: pinnedCode.filepath,
          line: pinnedCode.line,
          source_id: pinnedCode.sourceId || null,
          program: pinnedCode.program || null,
          section: pinnedCode.section || null,
          paragraph: pinnedCode.paragraph || null
        }] : [],
        ...extraMetadata
      }
    };

    const activeProfile = llmProfiles.find(p => p.id === activeProfileId);

    // Add placeholder assistant message
    const assistantPlaceholder = {
      role: 'assistant',
      content: "",
      sources: [],
      metadata: {
        model: activeProfile?.name || activeProfile?.model || "Default Model",
        provider: activeProfile?.provider,
        agent_steps: []
      }
    };

    const targetIndex = chatMessages.length + 1;
    setChatMessages(prev => [...prev, newUserMsg, assistantPlaceholder]);
    setCurrentMessage("");
    setIsLoading(true);
    const textareaEl = document.getElementById("chat-textarea") as HTMLTextAreaElement | null;
    if (textareaEl) textareaEl.style.height = 'auto';

    // The pin stays attached across messages until the user removes it manually
    // (via the X on its chip) — it's the ongoing subject of the conversation,
    // not a one-shot attachment.
    const currentPinned = pinnedCode;

    await runChatStream({
      message: userMsgContent,
      session_id: activeSessionId,
      project_id: selectedProject?.id,
      source_id: selectedSource?.id || null,
      branch: branch,
      pinned_file: currentPinned?.filepath || null,
      pinned_line: currentPinned?.line || null,
      pinned_context: currentPinned?.context || null,
      temperature: temperature,
      system_prompt: systemPrompt,
      llm_provider: activeProfile?.provider || "ollama",
      llm_model: activeProfile?.model || undefined,
      llm_api_key: activeProfile?.apiKey || undefined,
      llm_base_url: activeProfile?.baseUrl || undefined,
      metadata: newUserMsg.metadata
    }, targetIndex);
  };

  // Regenerates the assistant answer at `index` in place — the old answer is
  // deleted server-side and replaced (see retry_of_message_id in /chat), so the
  // history doesn't grow a duplicate question+answer pair like a fresh send would.
  const handleRetryMessage = async (index: number) => {
    if (isLoading) return;
    const assistantMsg: any = chatMessages[index];
    const userMsg: any = chatMessages[index - 1];
    if (!assistantMsg || assistantMsg.role !== 'assistant' || !assistantMsg.id) return;
    if (!userMsg || userMsg.role !== 'user') return;

    const activeProfile = llmProfiles.find(p => p.id === activeProfileId);
    const retryPlaceholder = {
      role: 'assistant',
      content: "",
      sources: [],
      metadata: {
        model: activeProfile?.name || activeProfile?.model || "Default Model",
        provider: activeProfile?.provider,
        agent_steps: []
      }
    };

    setChatMessages(prev => {
      const next = [...prev];
      next[index] = retryPlaceholder;
      return next;
    });
    setIsLoading(true);

    await runChatStream({
      message: userMsg.content,
      session_id: activeSessionId,
      project_id: selectedProject?.id,
      source_id: selectedSource?.id || null,
      branch: branch,
      pinned_file: pinnedCode?.filepath || null,
      pinned_line: pinnedCode?.line || null,
      pinned_context: pinnedCode?.context || null,
      temperature: temperature,
      system_prompt: systemPrompt,
      llm_provider: activeProfile?.provider || "ollama",
      llm_model: activeProfile?.model || undefined,
      llm_api_key: activeProfile?.apiKey || undefined,
      llm_base_url: activeProfile?.baseUrl || undefined,
      metadata: userMsg.metadata,
      retry_of_message_id: assistantMsg.id
    }, index);
  };

  // Optimistic toggle: clicking the same rating again clears it, matches how the
  // buttons visually behave (active/filled vs. outline) in ChatView.
  const handleFeedback = async (messageId: number, feedback: 'up' | 'down') => {
    const current = (chatMessages.find((m: any) => m.id === messageId) as any)?.feedback ?? null;
    const nextValue = current === feedback ? null : feedback;

    setChatMessages(prev => prev.map((m: any) => m.id === messageId ? { ...m, feedback: nextValue } : m));

    try {
      await api.updateChatMessageFeedback(messageId, nextValue);
    } catch (err) {
      console.error(err);
      setChatMessages(prev => prev.map((m: any) => m.id === messageId ? { ...m, feedback: current } : m));
      showToast(t('page.toast.feedbackFailed'), "error");
    }
  };

  const handleSessionSelect = async (session) => {
    ignoreUrlSyncRef.current = true;
    setActiveSessionId(session.id);

    // Update URL with session UUID
    if (session.uuid) {
      const params = new URLSearchParams(window.location.search);
      params.set('chat', session.uuid);
      router.push(`${pathname}?${params.toString()}`);
    }

    // Set focus if the session is linked to a project

    if (session.project) {
      const matchedProject = projects && projects.find((p: any) => p.id === session.project.id);
      handleProjectSelect(matchedProject || session.project);
    } else if (session.project_id && projects && projects.length > 0) {
      const matchedProject = projects.find((p: any) => p.id === session.project_id);
      if (matchedProject) {
        handleProjectSelect(matchedProject);
      }
    }

    // Set source focus if the session is linked to a source
    if (session.source) {
      setSelectedSource(session.source);
    } else if (session.source_id && connectedSources && connectedSources.length > 0) {
      const matchedSource = connectedSources.find((s: any) => s.id === session.source_id);
      if (matchedSource) {
        setSelectedSource(matchedSource);
      } else {
        setSelectedSource(null);
      }
    } else {
      setSelectedSource(null);
    }

    // Restore the workspace snapshot (panel layout + open files/docs/entities) if
    // this session has one — makes reopening/sharing a chat restore the whole
    // "situation", not just the message history. Older sessions have no
    // snapshot_json yet, so this falls back to the current single-panel default.
    const snap = session.snapshot_json;
    if (snap) {
      isRestoringSnapshotRef.current = true;

      if (!session.project && !session.project_id && snap.selectedProjectId && projects && projects.length > 0) {
        const matchedProject = projects.find((p: any) => p.id === snap.selectedProjectId);
        if (matchedProject) handleProjectSelect(matchedProject);
      }
      if (!session.source && !session.source_id && snap.selectedSourceId && connectedSources && connectedSources.length > 0) {
        const matchedSource = connectedSources.find((s: any) => s.id === snap.selectedSourceId);
        if (matchedSource) setSelectedSource(matchedSource);
      }

      const restoredSelections = Array.isArray(snap.panelSelections) && snap.panelSelections.length > 0
        ? snap.panelSelections
        : [{ selectedFile: null, selectedDoc: null, selectedEntity: null, selectedLine: null }];
      const primary = restoredSelections[0];

      // Global focus mirrors panel 0 — the unfrozen-panel sync effect (above) keys off these.
      setSelectedFile(primary.selectedFile ?? null);
      setSelectedDoc(primary.selectedDoc ?? null);
      setSelectedEntity(primary.selectedEntity ?? null);
      setSelectedLine(primary.selectedLine ?? null);

      setPanelConfigs(Array.isArray(snap.panelConfigs) && snap.panelConfigs.length > 0 ? snap.panelConfigs : ['chat']);
      setPanelFrozen(Array.isArray(snap.panelFrozen) ? snap.panelFrozen : restoredSelections.map(() => false));
      setPanelSelections(restoredSelections);
      setPanelFocusObject(Array.isArray(snap.panelFocusObject) ? snap.panelFocusObject : restoredSelections.map(() => null));
      setCollapsedPanels(restoredSelections.map(() => false));
      setFileNavStack(Array.isArray(snap.fileNavStack) ? snap.fileNavStack : []);
      setPinnedCode(snap.pinnedCode ?? null);
      if (typeof snap.activeRightTab === 'string') setActiveRightTab(snap.activeRightTab);
      if (typeof snap.splitPercent === 'number') setSplitPercent(snap.splitPercent);

      setTimeout(() => { isRestoringSnapshotRef.current = false; }, 0);
    }

    try {
      const res = await api.getChatMessages(session.id);
      const formatted = res.data.map((m: any) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        sources: m.sources_json || undefined,
        metadata: m.metadata_json || undefined,
        feedback: m.feedback || undefined
      }));
      setChatMessages(formatted);
      showToast(t('page.toast.sessionLoaded', { title: session.title }), "success");
    } catch (err) {
      console.error(err);
      showToast(t('page.toast.sessionLoadFailed'), "error");
    }
  };
  useEffect(() => {
    handleSessionSelectRef.current = handleSessionSelect;
  });

  const handleRemoveSession = async (id, e) => {
    e.stopPropagation();
    try {
      await api.deleteChatSession(id);
      setSessions(prev => prev.filter(s => s.id !== id));
      if (activeSessionId === id) {
        resetChatSession();
      }
      showToast(t('page.toast.sessionRemoved'), "success");
    } catch (err) {
      console.error(err);
      showToast(t('page.toast.sessionDeleteFailed'), "error");
    }
  };

  const handleOpenGraphView = () => {
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
  };

  const handleDividerMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingRef.current = true;
    setIsDragging(true);
    dragStartXRef.current = e.clientX;
    dragStartPercentRef.current = splitPercent;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  // Whichever knowledge object is focused in a panel — a code entity, a document,
  // a graph node, or a focused object — resolved into one shape so every view
  // can show the same focus bar, no matter which content type is active.
  const getPanelFocusInfo = (index: number, contentType: string, sel: {
    selectedFile: string | null;
    selectedDoc: any | null;
    selectedEntity: any | null;
    selectedLine: number | null;
  }): { Icon: any; label: string; kind: string; colorClass: string } | null => {
    const focusObject = panelFocusObject[index];
    if (focusObject) {
      return { Icon: Box, label: focusObject.name, kind: focusObject.kind || t('page.focusBar.entity'), colorClass: "text-ds-purple-400" };
    }
    if (sel.selectedEntity) {
      return { Icon: Braces, label: sel.selectedEntity.name, kind: sel.selectedEntity.type || t('page.focusBar.entity'), colorClass: "text-ds-indigo-400" };
    }
    if (sel.selectedDoc) {
      const isWeb = sel.selectedDoc.isWebOrigin ||
        ['confluence', 'jira'].includes((sel.selectedDoc.type || '').toLowerCase());
      // Local documents carry their storage path in .name (see handleDocFocusRequest) —
      // show just the filename here so the focus bar doesn't duplicate the path the
      // doc panel's own header already renders right below it.
      return {
        Icon: isWeb ? Globe : BookOpen,
        label: isWeb ? sel.selectedDoc.name : (sel.selectedDoc.name?.split('/').pop() || sel.selectedDoc.name),
        kind: isWeb ? t('page.focusBar.webOrigin') : t('page.focusBar.document'),
        colorClass: isWeb ? "text-ds-emerald-400" : "text-ds-orange-400"
      };
    }
    if (sel.selectedFile) {
      return { Icon: Terminal, label: sel.selectedFile, kind: t('page.focusBar.file'), colorClass: "text-ds-blue-400" };
    }
    return null;
  };

  const renderPanel = (index: number) => {
    const contentType = panelConfigs[index] || 'chat';
    // panelConfigs can grow independently of the mobile tab indices below —
    // fall back to an empty selection rather than crashing on out-of-range access.
    const sel = panelSelections[index] || { selectedFile: null, selectedDoc: null, selectedEntity: null, selectedLine: null };
    const focusInfo = getPanelFocusInfo(index, contentType, sel);

    const isChat = contentType === 'chat';

    const setContentType = (newType: string) => {
      setPanelConfigs(prev => {
        const next = [...prev];
        next[index] = newType;
        return next;
      });
      setPanelFocusObject(prev => {
        const next = [...prev];
        next[index] = null;
        return next;
      });
    };

    // Collapsed chat rail — the chat can be collapsed but never fully closed
    if (isChat && collapsedPanels[index]) {
      return (
        <button
          onClick={() => togglePanelCollapse(index)}
          title={t('page.workspace.expandChat')}
          className={cn(
            "h-full w-full flex flex-col items-center gap-3 py-3 border rounded-lg transition-colors cursor-pointer group",
            theme === 'dark'
              ? "bg-ds-zinc-950/40 border-ds-zinc-900 text-ds-zinc-400 hover:text-ds-indigo-400 hover:border-ds-zinc-800"
              : "bg-ds-white/40 border-ds-zinc-200 text-ds-zinc-500 hover:text-ds-indigo-600 hover:border-ds-zinc-300"
          )}
        >
          <span className={cn(
            "p-1.5 rounded-lg border",
            theme === 'dark' ? "border-ds-zinc-800 bg-ds-zinc-900/60" : "border-ds-zinc-200 bg-ds-zinc-50"
          )}>
            <ChevronRight className="w-3.5 h-3.5" />
          </span>
          <MessageSquare className="w-4 h-4 text-ds-indigo-500 shrink-0" />
          <span
            className="text-[10px] font-bold uppercase tracking-widest"
            style={{ writingMode: 'vertical-rl' }}
          >
            {t('page.mobileTab.chat')}
          </span>
        </button>
      );
    }

    return (
      <div
        className={cn(
          "h-full flex flex-col min-w-0 rounded-lg overflow-hidden relative group transition-all duration-300",
          panelFrozen[index] ? "border-2 border-ds-amber-500 shadow-[0_0_16px_rgba(245,158,11,0.55)]" : "border",
          theme === 'dark'
            ? (panelFrozen[index] ? "bg-ds-zinc-955" : "bg-ds-zinc-950/40 border-ds-zinc-900")
            : (panelFrozen[index] ? "bg-ds-amber-50/5" : "bg-ds-white/40 border-ds-zinc-200")
        )}
        style={(!panelFrozen[index] && selectedProject?.color) ? {
          boxShadow: `0 4px 20px rgba(0, 0, 0, 0.05), 0 0 15px ${selectedProject.color}${theme === 'dark' ? '12' : '08'}`,
          borderColor: `${selectedProject.color}25`
        } : undefined}
      >
        {/* Panel Header Selector */}
        <div className={cn(
          "px-3 py-1.5 border-b flex items-center justify-between shrink-0 z-20 backdrop-blur-md select-none transition-colors duration-300",
          theme === 'dark'
            ? (panelFrozen[index] ? "border-ds-amber-500/20 bg-ds-zinc-950/60" : "border-ds-zinc-900 bg-ds-zinc-950/60")
            : (panelFrozen[index] ? "border-ds-amber-500/20 bg-ds-zinc-50/60" : "border-ds-zinc-200 bg-ds-zinc-50/60")
        )}>
          <div className="flex items-center gap-1.5">
            <Select value={contentType} onValueChange={setContentType}>
              <SelectTrigger aria-label={t('page.panelTypeSelectorLabel')} className={cn(
                "h-6 text-[10px] bg-transparent border-0 font-bold uppercase tracking-wider focus:ring-0 focus:ring-offset-0 px-1 py-0 gap-1.5 w-auto transition-colors duration-200",
                panelFrozen[index]
                  ? "text-ds-amber-500 hover:text-ds-amber-400"
                  : "text-ds-indigo-400 hover:text-ds-indigo-350"
              )}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className={theme === 'dark' ? "bg-ds-zinc-950 border-ds-zinc-900 text-ds-zinc-100" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-900"}>
                <SelectItem value="chat" className="text-xs">{t('page.viewTypes.chat')}</SelectItem>
                <SelectItem value="code" className="text-xs">{t('page.viewTypes.code')}</SelectItem>
                <SelectItem value="doc" className="text-xs">{t('page.viewTypes.doc')}</SelectItem>
                <SelectItem value="graph" className="text-xs">{t('page.viewTypes.graph')}</SelectItem>
                <SelectItem value="callgraph" className="text-xs">{t('page.viewTypes.callgraph')}</SelectItem>
                <SelectItem value="webview" className="text-xs">{t('page.viewTypes.webview')}</SelectItem>
                {features.views.linkManager && (
                  <SelectItem value="linkmanager" className="text-xs">{t('page.viewTypes.linkmanager')}</SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => togglePanelFreeze(index)}
              className={cn(
                "p-1 rounded border transition-all duration-150 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider cursor-pointer",
                panelFrozen[index]
                  ? "bg-ds-amber-500/10 border-ds-amber-500/30 text-ds-amber-500 hover:bg-ds-amber-500/20"
                  : (theme === 'dark'
                      ? "bg-transparent border-ds-zinc-800 text-ds-zinc-500 hover:text-ds-zinc-300 hover:border-ds-zinc-700"
                      : "bg-transparent border-ds-zinc-200 text-ds-zinc-400 hover:text-ds-zinc-700 hover:border-ds-zinc-300")
              )}
              title={panelFrozen[index] ? "Auto-Refresh pausiert (Klicken zum Aktivieren)" : "Auto-Refresh aktiv (Klicken zum Pausieren)"}
            >
              {panelFrozen[index] ? (
                <>
                  <Lock className="w-3 h-3 text-ds-amber-500" />
                  <span className="text-[9px] text-ds-amber-500 hidden sm:inline">Fixiert</span>
                </>
              ) : (
                <>
                  <RefreshCw className="w-3 h-3 text-ds-emerald-500 animate-[spin_8s_linear_infinite]" />
                  <span className="text-[9px] text-ds-zinc-500 hidden sm:inline">Live</span>
                </>
              )}
            </button>
            {(contentType === 'code' || contentType === 'doc') && (
              <button
                onClick={() => setIsReferencesDropdownOpen(!isReferencesDropdownOpen)}
                className={cn(
                  "p-1 rounded border transition-all duration-155 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider cursor-pointer",
                  isReferencesDropdownOpen
                    ? "bg-ds-indigo-500/10 border-ds-indigo-500/30 text-ds-indigo-400 hover:bg-ds-indigo-500/20"
                    : (theme === 'dark'
                        ? "bg-transparent border-ds-zinc-800 text-ds-zinc-500 hover:text-ds-zinc-300 hover:border-ds-zinc-700"
                        : "bg-transparent border-ds-zinc-200 text-ds-zinc-405 hover:text-ds-zinc-700 hover:border-ds-zinc-300")
                )}
                title="Referenzen & Verknüpfte Dokumente"
              >
                <Link2 className="w-3 h-3 text-ds-indigo-400" />
                <span className="text-[9px] text-ds-zinc-500 hidden sm:inline">Referenzen</span>
                {fileReferences.length > 0 && (
                  <span className={cn(
                    "px-1 py-0.2 text-[8px] font-bold rounded-sm leading-none",
                    theme === 'dark' ? "bg-ds-indigo-500/20 text-ds-indigo-300" : "bg-ds-indigo-100 text-ds-indigo-700"
                  )}>
                    {fileReferences.length}
                  </span>
                )}
              </button>
            )}
            {isChat ? (
              /* The chat can only be collapsed, never fully closed */
              <button
                onClick={() => togglePanelCollapse(index)}
                className={cn(
                  "p-1 rounded border transition-all duration-150 flex items-center justify-center cursor-pointer",
                  theme === 'dark'
                    ? "bg-transparent border-ds-zinc-800 text-ds-zinc-550 hover:text-ds-indigo-400 hover:border-ds-indigo-900/40 hover:bg-ds-indigo-950/20"
                    : "bg-transparent border-ds-zinc-200 text-ds-zinc-400 hover:text-ds-indigo-600 hover:border-ds-indigo-200 hover:bg-ds-indigo-50"
                )}
                title={t('page.workspace.collapseChat')}
              >
                <ChevronLeft className="w-3 h-3" />
              </button>
            ) : panelConfigs.length > 1 && (
              <button
                onClick={() => {
                  setPanelConfigs(prev => prev.filter((_, idx) => idx !== index));
                  setPanelFrozen(prev => prev.filter((_, idx) => idx !== index));
                  setCollapsedPanels(prev => prev.filter((_, idx) => idx !== index));
                  setPanelSelections(prev => prev.filter((_, idx) => idx !== index));
                  setPanelFocusObject(prev => prev.filter((_, idx) => idx !== index));
                }}
                className={cn(
                  "p-1 rounded border transition-all duration-150 flex items-center justify-center cursor-pointer",
                  theme === 'dark'
                    ? "bg-transparent border-ds-zinc-800 text-ds-zinc-550 hover:text-ds-red-400 hover:border-ds-red-900/40 hover:bg-ds-red-950/20"
                    : "bg-transparent border-ds-zinc-200 text-ds-zinc-400 hover:text-ds-red-500 hover:border-ds-red-200 hover:bg-ds-red-50"
                )}
                title={t('page.workspace.closeView')}
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>

        {/* Focus Bar — always shows which knowledge object (file, doc, code entity,
            graph node, fokussiertes Objekt, ...) the panel below currently relates to, so the
            user can tell context apart at a glance regardless of which view is active. */}
        {contentType !== 'doc' && contentType !== 'webview' && contentType !== 'linkmanager' && (
          <div className={cn(
            "px-3 py-1 border-b flex items-center gap-1.5 text-[11px] shrink-0 z-10 min-w-0",
            theme === 'dark' ? "border-ds-zinc-900 bg-ds-zinc-950/40" : "border-ds-zinc-200 bg-ds-zinc-50/40"
          )}>
            {focusInfo ? (
              <>
                <focusInfo.Icon className={cn("w-3 h-3 shrink-0", focusInfo.colorClass)} />
                {contentType !== 'webview' && (
                  <>
                    <span
                      className={cn("truncate font-medium", theme === 'dark' ? "text-ds-zinc-300" : "text-ds-zinc-700")}
                      title={focusInfo.label}
                    >
                      {focusInfo.label}
                    </span>
                    <span className="text-ds-zinc-600 shrink-0">·</span>
                  </>
                )}
                <span className="text-ds-zinc-500 uppercase tracking-wide text-[9px] shrink-0">{focusInfo.kind}</span>
              </>
            ) : (
              <span className="text-ds-zinc-600 italic">{t('page.focusBar.none')}</span>
            )}
          </div>
        )}

        {/* Panel Content Renderer */}
        <div className="flex-1 min-w-0 min-h-0 overflow-hidden relative">
          {contentType === 'chat' && (
            <ChatView
              theme={theme}
              isSidebarOpen={isSidebarOpen}
              selectedProject={selectedProject}
              setSelectedProject={setSelectedProject}
              setFiles={setFiles}
              pinnedCode={pinnedCode}
              setPinnedCode={setPinnedCode}
              chatMessages={chatMessages}
              currentMessage={currentMessage}
              setCurrentMessage={setCurrentMessage}
              isLoading={isLoading}
              activeSessionId={activeSessionId}
              handleSendChat={handleSendChat}
              handleRetryMessage={handleRetryMessage}
              handleFeedback={handleFeedback}
              handleFileSelect={(path, line, sourceId) => handlePanelFileSelect(index, path, line, sourceId)}
              activeProfileId={activeProfileId}
              setActiveProfileId={setActiveProfileId}
              llmProfiles={llmProfiles}
              showToast={showToast}
              selectedFile={sel.selectedFile}
              selectedDoc={sel.selectedDoc}
              splitClasses={{ chat: "w-full", editor: "w-full" }}
              chatEndRef={chatEndRef}
              selectedSource={selectedSource}
              setSelectedSource={setSelectedSource}
              connectedSources={connectedSources}
            />
          )}

          {contentType === 'code' && (
            <SplitPaneWorkspace
              theme={theme}
              selectedFile={sel.selectedFile}
              selectedDoc={sel.selectedDoc}
              selectedLine={sel.selectedLine}
              activeRightTab="code"
              setActiveRightTab={() => {}}
              isEditorMaximized={false}
              setIsEditorMaximized={() => {}}
              setSelectedFile={(path) => handlePanelFileSelect(index, path)}
              setSelectedDoc={(doc) => handlePanelFileSelect(index, doc?.name || null, null, doc?.id || null)}
              handleFileSelect={(path, line, sourceId) => handlePanelFileSelect(index, path, line, sourceId)}
              isReferencesDropdownOpen={isReferencesDropdownOpen}
              setIsReferencesDropdownOpen={setIsReferencesDropdownOpen}
              referencesTab={referencesTab}
              setReferencesTab={setReferencesTab}
              selectedEntity={sel.selectedEntity}
              splitClasses={{ chat: "w-full", editor: "w-full" }}
              activeLlmModel={activeLlmModel}
              activeEmbeddingModel={activeEmbeddingModel}
              editorFontSize={editorFontSize}
              editorFontFamily={editorFontFamily}
              editorMinimap={editorMinimap}
              selectedProject={selectedProject}
              projectEntities={projectEntities}
              handleEntitySelect={(ent) => handlePanelEntitySelect(index, ent)}
              onGutterClick={(lineNumber, lineContent) => handleGutterClick(index, lineNumber, lineContent)}
              onGutterAskEntity={(entity) => handleGutterAskEntity(index, entity)}
              fileNavStack={fileNavStack}
              onNavigateBack={handleNavigateBack}
            />
          )}

          {contentType === 'doc' && (
            <SplitPaneWorkspace
              theme={theme}
              selectedFile={sel.selectedFile}
              selectedDoc={sel.selectedDoc}
              selectedLine={sel.selectedLine}
              activeRightTab="doc"
              setActiveRightTab={() => {}}
              isEditorMaximized={false}
              setIsEditorMaximized={() => {}}
              setSelectedFile={(path) => handlePanelFileSelect(index, path)}
              setSelectedDoc={(doc) => handlePanelFileSelect(index, doc?.name || null, null, doc?.id || null)}
              handleFileSelect={(path, line, sourceId) => handlePanelFileSelect(index, path, line, sourceId)}
              isReferencesDropdownOpen={isReferencesDropdownOpen}
              setIsReferencesDropdownOpen={setIsReferencesDropdownOpen}
              referencesTab={referencesTab}
              setReferencesTab={setReferencesTab}
              selectedEntity={sel.selectedEntity}
              splitClasses={{ chat: "w-full", editor: "w-full" }}
              activeLlmModel={activeLlmModel}
              activeEmbeddingModel={activeEmbeddingModel}
              editorFontSize={editorFontSize}
              editorFontFamily={editorFontFamily}
              editorMinimap={editorMinimap}
              selectedProject={selectedProject}
              projectEntities={projectEntities}
              handleEntitySelect={(ent) => handlePanelEntitySelect(index, ent)}
              onGutterClick={(lineNumber, lineContent) => handleGutterClick(index, lineNumber, lineContent)}
              onGutterAskEntity={(entity) => handleGutterAskEntity(index, entity)}
              fileNavStack={fileNavStack}
              onNavigateBack={handleNavigateBack}
            />
          )}

          {contentType === 'graph' && (
            <SplitPaneWorkspace
              theme={theme}
              selectedFile={sel.selectedFile}
              selectedDoc={sel.selectedDoc}
              selectedLine={sel.selectedLine}
              activeRightTab="graph"
              setActiveRightTab={() => {}}
              isEditorMaximized={false}
              setIsEditorMaximized={() => {}}
              setSelectedFile={(path) => handlePanelFileSelect(index, path)}
              setSelectedDoc={(doc) => handlePanelFileSelect(index, doc?.name || null, null, doc?.id || null)}
              handleFileSelect={(path, line, sourceId, openIfMissing) => handlePanelFileSelect(index, path, line, sourceId, openIfMissing)}
              isReferencesDropdownOpen={isReferencesDropdownOpen}
              setIsReferencesDropdownOpen={setIsReferencesDropdownOpen}
              referencesTab={referencesTab}
              setReferencesTab={setReferencesTab}
              selectedEntity={sel.selectedEntity}
              splitClasses={{ chat: "w-full", editor: "w-full" }}
              activeLlmModel={activeLlmModel}
              activeEmbeddingModel={activeEmbeddingModel}
              editorFontSize={editorFontSize}
              editorFontFamily={editorFontFamily}
              editorMinimap={editorMinimap}
              selectedProject={selectedProject}
              projectEntities={projectEntities}
              handleEntitySelect={(ent) => handlePanelEntitySelect(index, ent)}
              onGutterClick={(lineNumber, lineContent) => handleGutterClick(index, lineNumber, lineContent)}
              onGutterAskEntity={(entity) => handleGutterAskEntity(index, entity)}
              fileNavStack={fileNavStack}
              onNavigateBack={handleNavigateBack}
              onDocFocus={handleDocFocusRequest}
              layoutMode={layoutMode}
            />
          )}

          {contentType === 'callgraph' && (
            <CallGraphView
              theme={theme}
              focusedEntity={sel.selectedEntity}
              projectId={selectedProject?.id}
              onFileSelect={(path, line, sourceId) => handlePanelFileSelect(index, path, line, sourceId)}
            />
          )}

          {contentType === 'webview' && (
            <SplitPaneWorkspace
              theme={theme}
              selectedFile={sel.selectedFile}
              selectedDoc={sel.selectedDoc}
              selectedLine={sel.selectedLine}
              activeRightTab="weborigin"
              setActiveRightTab={() => {}}
              isEditorMaximized={false}
              setIsEditorMaximized={() => {}}
              setSelectedFile={(path) => handlePanelFileSelect(index, path)}
              setSelectedDoc={(doc) => handlePanelFileSelect(index, doc?.name || null, null, doc?.id || null)}
              handleFileSelect={(path, line, sourceId) => handlePanelFileSelect(index, path, line, sourceId)}
              isReferencesDropdownOpen={isReferencesDropdownOpen}
              setIsReferencesDropdownOpen={setIsReferencesDropdownOpen}
              referencesTab={referencesTab}
              setReferencesTab={setReferencesTab}
              selectedEntity={sel.selectedEntity}
              splitClasses={{ chat: "w-full", editor: "w-full" }}
              activeLlmModel={activeLlmModel}
              activeEmbeddingModel={activeEmbeddingModel}
              editorFontSize={editorFontSize}
              editorFontFamily={editorFontFamily}
              editorMinimap={editorMinimap}
              selectedProject={selectedProject}
              projectEntities={projectEntities}
              handleEntitySelect={(ent) => handlePanelEntitySelect(index, ent)}
              onGutterClick={(lineNumber, lineContent) => handleGutterClick(index, lineNumber, lineContent)}
              onGutterAskEntity={(entity) => handleGutterAskEntity(index, entity)}
              fileNavStack={fileNavStack}
              onNavigateBack={handleNavigateBack}
            />
          )}

          {contentType === 'linkmanager' && (
            <LinkManagerView
              selectedProject={selectedProject}
              theme={theme}
              currentUser={currentUser}
              llmProfiles={llmProfiles}
              activeProfileId={activeProfileId}
              setActiveProfileId={setActiveProfileId}
              showToast={showToast}
            />
          )}

        </div>
      </div>
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
        value={{
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
        }}
      >
        <SettingsModal
          isOpen={isSettingsOpen}
          onClose={() => setIsSettingsOpen(false)}
        />
      </SettingsProvider>

      {/* Header bar: search (feature-gated), sidebar toggle, and the app-level
          actions (graph, theme, settings) — always mounted so those actions
          stay reachable even if the search feature is disabled. Link Manager
          is no longer a dedicated header action — it's opened like any other
          panel type via the "+" add-view menu or a panel's type selector. */}
      <GlobalSearch
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
      <Sidebar
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
        handleFileSelect={(path, line, sourceId) => {
          pinFileFocus(path, line);
          return handleFileSelect(path, line, sourceId);
        }}
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

        {/* Mobile View Toggle Bar */}
        {(selectedFile || selectedDoc || activeRightTab === 'graph') && (
          <div className={cn(
            "flex md:hidden border-b p-2 gap-2 justify-center shrink-0 z-20",
            theme === 'dark' ? "border-ds-zinc-800 bg-ds-zinc-900/40" : "border-ds-zinc-200 bg-ds-zinc-100/50"
          )}>
            <Button
              variant={activeMobileTab === 'chat' ? 'default' : 'ghost'}
              onClick={() => setActiveMobileTab('chat')}
              className={cn(
                "flex-1 text-xs gap-1.5 h-8 rounded-lg font-bold",
                activeMobileTab === 'chat' && "bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-550"
              )}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>{t('page.mobileTab.chat')}</span>
            </Button>
            <Button
              variant={activeMobileTab === 'editor' ? 'default' : 'ghost'}
              onClick={() => {
                setActiveMobileTab('editor');
                if (activeRightTab === 'graph') {
                  if (selectedFile) setActiveRightTab('code');
                  else if (selectedDoc) setActiveRightTab('doc');
                }
              }}
              className={cn(
                "flex-1 text-xs gap-1.5 h-8 rounded-lg font-bold",
                activeMobileTab === 'editor' && "bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-550"
              )}
            >
              <Code className="w-3.5 h-3.5" />
              <span>{t('page.mobileTab.editor')}</span>
            </Button>
            <Button
              variant={activeMobileTab === 'graph' ? 'default' : 'ghost'}
              onClick={() => {
                setActiveMobileTab('graph');
                setActiveRightTab('graph');
              }}
              className={cn(
                "flex-1 text-xs gap-1.5 h-8 rounded-lg font-bold",
                activeMobileTab === 'graph' && "bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-550"
              )}
            >
              <Network className="w-3.5 h-3.5" />
              <span>{t('page.mobileTab.graph')}</span>
            </Button>
          </div>
        )}

        {/* DYNAMIC PANEL WORKSPACE */}
        <div ref={splitContainerRef} className="flex-1 flex overflow-hidden z-10 mt-1">
          {isMobile ? (
            <div className="flex-1 p-2 h-full">
              {/* Panels now open on demand at whatever index is next free, so
                  look up each tab's panel by type instead of assuming a fixed slot. */}
              {activeMobileTab === 'chat' && renderPanel(panelConfigs.indexOf('chat'))}
              {activeMobileTab === 'editor' && renderPanel(panelConfigs.findIndex(c => c !== 'chat' && c !== 'graph'))}
              {activeMobileTab === 'graph' && renderPanel(panelConfigs.indexOf('graph'))}
            </div>
          ) : (
            // One stable container mapped over panelConfigs, instead of four mutually-exclusive
            // `{layoutMode === 'x' && <div>...}` siblings: since only one of those ever rendered,
            // switching layoutMode (any panel open/close) flipped a whole subtree from an element
            // to `false` and back, which React always unmounts — wiping panel-internal state (e.g.
            // the graph's zoom/pan/selection) instead of just resizing it in place.
            <div
              className={cn(
                "flex-1 p-2 h-full overflow-hidden",
                layoutMode === '4-grid'
                  ? "grid grid-cols-2 grid-rows-2 gap-2"
                  : cn("flex", layoutMode !== '1-pane' && "gap-2")
              )}
            >
              {panelConfigs.map((_, i) => (
                <React.Fragment key={i}>
                  {layoutMode === 'split' && i === 1 && (
                    // DRAGGABLE DIVIDER
                    <div
                      onMouseDown={handleDividerMouseDown}
                      className="hidden md:flex w-1 shrink-0 cursor-col-resize items-center justify-center group z-20 relative"
                    >
                      <div className={cn(
                        "absolute inset-y-0 -left-1 -right-1",
                        isDragging ? "bg-ds-indigo-500/20" : "group-hover:bg-ds-indigo-500/10"
                      )} />
                      <div className={cn(
                        "w-0.5 h-10 rounded-full transition-colors relative z-10",
                        isDragging ? "bg-ds-indigo-500" : "bg-ds-zinc-700 group-hover:bg-ds-indigo-400"
                      )} />
                    </div>
                  )}
                  {layoutMode === 'split' && i === 0 ? (
                    <div
                      style={isPanelCollapsed(0) ? undefined : { width: `${splitPercent}%` }}
                      className={cn(
                        "h-full flex flex-col min-w-0",
                        isPanelCollapsed(0) && "flex-none w-12",
                        !isDragging && "transition-all duration-300"
                      )}
                    >
                      {renderPanel(0)}
                    </div>
                  ) : (
                    <div className={cellCls(i, "flex-1")}>
                      {renderPanel(i)}
                    </div>
                  )}
                </React.Fragment>
              ))}
            </div>
          )}
        </div>
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
