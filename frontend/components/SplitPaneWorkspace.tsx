import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import Editor from '@monaco-editor/react';
import { AnimatePresence } from 'framer-motion';

import {
  Terminal,
  Link2,
  Layers,
  X,
  BookOpen,
  Activity,
  ExternalLink,
  FileCode,
  Loader2,
  Code,
  Globe,
  FileText,
  Network,
  Download,
  ChevronLeft,
  ChevronRight,
  Sparkles
} from 'lucide-react';
import { KnowledgeGraphView } from './KnowledgeGraphView';

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MarkdownContent } from "@/components/MarkdownContent";
import { cn } from "@/lib/utils";
import { sanitizeHtml } from "@/lib/sanitize";
import { api, API_URL } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';

const RULER_COLUMNS = Array.from({ length: 160 }, (_, i) => i + 1);

// Help detect file extensions in Monaco editor
const detectLanguage = (filename: string | null) => {
  if (!filename) return 'text';
  const ext = filename.split('.').pop()?.toLowerCase();
  switch(ext) {
    case 'py': return 'python';
    case 'cob':
    case 'cbl':
    case 'cpy': return 'cobol';
    case 'js':
    case 'jsx': return 'javascript';
    case 'ts':
    case 'tsx': return 'typescript';
    case 'json': return 'json';
    case 'md': return 'markdown';
    case 'html': return 'html';
    case 'css': return 'css';
    case 'sh': return 'shell';
    case 'yml':
    case 'yaml': return 'yaml';
    case 'java': return 'java';
    case 'c': return 'c';
    case 'cpp':
    case 'cc':
    case 'h':
    case 'hpp': return 'cpp';
    case 'cs': return 'csharp';
    default: return 'text';
  }
};

interface SplitPaneWorkspaceProps {
  theme: string;
  selectedFile: any | null;
  selectedDoc: any | null;
  activeRightTab: 'code' | 'doc' | 'weborigin' | 'graph';
  setActiveRightTab: (tab: 'code' | 'doc' | 'weborigin' | 'graph') => void;
  selectedProject?: any | null;
  isEditorMaximized: boolean;
  setIsEditorMaximized: (max: boolean) => void;
  setSelectedFile: (file: any | null) => void;
  setSelectedDoc: (doc: any | null) => void;
  fileContent?: string;
  fileContentFormat?: string;
  handleFileSelect: (path: string, line?: number | null, sourceId?: number | string | null, openIfMissing?: boolean) => Promise<void>;
  isLoadingFile?: boolean;

  // Monaco ref passed from parent to allow scrolling & decorations from page.tsx
  editorRef?: React.MutableRefObject<any>;

  // References Tab Props
  fileReferences?: any[];
  isLoadingReferences?: boolean;
  isReferencesDropdownOpen: boolean;
  setIsReferencesDropdownOpen: (open: boolean) => void;
  referencesTab: 'code' | 'docs';
  setReferencesTab: (tab: 'code' | 'docs') => void;
  selectedEntity: any | null;
  splitClasses: { chat: string; editor: string };
  activeLlmModel: string;
  activeEmbeddingModel: string;
  editorFontSize: number;
  editorFontFamily: string;
  editorMinimap: boolean;
  projectEntities?: any[];
  handleEntitySelect?: (ent: any) => Promise<void> | void;
  onGutterClick?: (lineNumber: number, lineContent: string) => void;
  onGutterAskEntity?: (entity: any) => void;
  fileNavStack?: Array<{file: string|null, doc: any|null, tab: string}>;
  onNavigateBack?: () => void;
  selectedLine?: number | null;
  onDocFocus?: (filePath: string, sourceId: number | string | null) => void;
  // How many panels are currently open in the workspace grid — lets the graph
  // view swap its detail sidebar for a space-saving bottom drawer once 3+ panels
  // are open (see KnowledgeGraphView's layoutMode prop).
  layoutMode?: '1-pane' | 'split' | '3-col' | '4-grid';
}

export const SplitPaneWorkspace: React.FC<SplitPaneWorkspaceProps> = ({
  theme,
  selectedFile,
  selectedDoc,
  activeRightTab,
  setActiveRightTab,
  isEditorMaximized,
  setIsEditorMaximized,
  setSelectedFile,
  setSelectedDoc,
  fileContent,
  fileContentFormat,
  handleFileSelect,
  isLoadingFile,
  editorRef,
  fileReferences,
  isLoadingReferences,
  isReferencesDropdownOpen,
  setIsReferencesDropdownOpen,
  referencesTab,
  setReferencesTab,
  selectedEntity,
  splitClasses,
  activeLlmModel,
  activeEmbeddingModel,
  editorFontSize,
  editorFontFamily,
  editorMinimap,
  selectedProject = null,
  projectEntities = [],
  handleEntitySelect,
  onGutterClick,
  onGutterAskEntity,
  fileNavStack = [],
  onNavigateBack,
  selectedLine = null,
  onDocFocus,
  layoutMode
}) => {
  const { t } = useLanguage();
  const [cursorColumn, setCursorColumn] = useState<number>(1);
  const [editorContentLeft, setEditorContentLeft] = useState<number>(53);
  const [isReferencesModalMode, setIsReferencesModalMode] = useState<boolean>(false);
  const [focusedRefNode, setFocusedRefNode] = useState<any | null>(null);
  const [focusedRefReferences, setFocusedRefReferences] = useState<any[]>([]);
  const [isLoadingFocusedRefRefs, setIsLoadingFocusedRefRefs] = useState<boolean>(false);
  const [entityNeighborGroups, setEntityNeighborGroups] = useState<Record<string, any[]>>({});
  const [isLoadingEntityNeighbors, setIsLoadingEntityNeighbors] = useState(false);

  const [localFileContent, setLocalFileContent] = useState<string>("");
  const [localFileContentFormat, setLocalFileContentFormat] = useState<string>("text");
  const [localIsLoadingFile, setLocalIsLoadingFile] = useState<boolean>(false);
  const [localFileReferences, setLocalFileReferences] = useState<any[]>([]);
  const [localIsLoadingReferences, setLocalIsLoadingReferences] = useState<boolean>(false);

  const contentToUse = fileContent !== undefined ? fileContent : localFileContent;
  const formatToUse = fileContentFormat !== undefined ? fileContentFormat : localFileContentFormat;
  const isLoadingToUse = isLoadingFile !== undefined ? isLoadingFile : localIsLoadingFile;
  const referencesToUse = fileReferences !== undefined ? fileReferences : localFileReferences;
  const isLoadingRefsToUse = isLoadingReferences !== undefined ? isLoadingReferences : localIsLoadingReferences;
  // Die Dropdown-Liste zeigt im Code-Tab entityNeighborGroups (pro Fokusobjekt),
  // nicht referencesToUse (das ist nur der Inhalt des Doc-Tabs) — das Badge muss
  // dieselbe Quelle zählen, sonst bleibt die Ziffer beim Wechsel des im Code
  // angeklickten Objekts auf dem Dateistand stehen.
  const referenceBadgeCount = activeRightTab === 'code'
    ? Object.values(entityNeighborGroups).reduce((sum, group) => sum + group.length, 0)
    : referencesToUse.length;

  useEffect(() => {
    if (!selectedEntity?.id || activeRightTab !== 'code') {
      // queueMicrotask: a direct setState call here reads as synchronous
      // setState-in-effect to the compiler's analysis.
      queueMicrotask(() => { setEntityNeighborGroups({}); });
      return;
    }
    let cancelled = false;
    // queueMicrotask: a direct setState call here reads as synchronous
    // setState-in-effect to the compiler's analysis.
    queueMicrotask(() => { setIsLoadingEntityNeighbors(true); });
    api.getEntityNeighbors(selectedEntity.id, { projectId: selectedProject?.id })
      .then((response) => {
        if (!cancelled) setEntityNeighborGroups(response.data?.groups || {});
      })
      .catch((error) => {
        console.error('Failed to load entity neighbors:', error);
        if (!cancelled) setEntityNeighborGroups({});
      })
      .finally(() => {
        if (!cancelled) setIsLoadingEntityNeighbors(false);
      });
    return () => { cancelled = true; };
  }, [selectedEntity?.id, activeRightTab, selectedProject?.id]);

  const neighborGroupLabels: Record<string, string> = {
    'CALL:in': t('splitPane.neighborGroupLabels.callIn'),
    'CALL:out': t('splitPane.neighborGroupLabels.callOut'),
    'COPY:out': t('splitPane.neighborGroupLabels.copyOut'),
    'COPY:in': t('splitPane.neighborGroupLabels.copyIn'),
    'READS:out': t('splitPane.neighborGroupLabels.readsOut'),
    'WRITES:out': t('splitPane.neighborGroupLabels.writesOut'),
    'PERFORM:out': t('splitPane.neighborGroupLabels.performOut'),
    'PERFORM:in': t('splitPane.neighborGroupLabels.performIn'),
    'GOTO:out': t('splitPane.neighborGroupLabels.gotoOut'),
    'USES:out': t('splitPane.neighborGroupLabels.usesOut'),
    'USES:in': t('splitPane.neighborGroupLabels.usesIn'),
    'DOC:out': t('splitPane.neighborGroupLabels.docOut'),
  };

  const localEditorRef = useRef<any>(null);
  const activeEditorRef = editorRef || localEditorRef;

  // Local file loading effect — the graph pane renders KnowledgeGraphView straight
  // off selectedFile/selectedDoc/selectedEntity and never touches contentToUse, so
  // skip fetching content for it entirely rather than syncing something unused.
  useEffect(() => {
    if (activeRightTab === 'graph') return;

    const loadContent = async () => {
      let path = selectedFile;
      let docId = selectedDoc?.id;
      let isDoc = !!selectedDoc;

      if (!path && !selectedDoc) {
        setLocalFileContent("");
        setLocalFileContentFormat("text");
        return;
      }

      // Images are rendered directly via the /raw endpoint (see render below) —
      // reading them as text through /content would just yield garbled bytes.
      const isImage = /\.(png|jpe?g)$/i.test((selectedDoc?.name || path || ""));
      if (isDoc && isImage) {
        setLocalFileContent("");
        setLocalFileContentFormat("image");
        setLocalIsLoadingFile(false);
        return;
      }

      setLocalIsLoadingFile(true);
      setLocalFileContent("");
      try {
        if (isDoc) {
          const isWeb = selectedDoc.isWebOrigin ||
            (selectedDoc.type?.toLowerCase() === 'confluence' ||
             selectedDoc.type?.toLowerCase() === 'jira' ||
             selectedDoc.type?.toLowerCase() === 'jira');

          if (isWeb) {
            const res = await api.resolveWebOrigin(docId, selectedDoc.url || selectedDoc.name, theme);
            setLocalFileContent(res.data.content);
            setLocalFileContentFormat("html");
          } else {
            const res = await api.getKnowledgeSourceContent(docId, selectedDoc.name);
            setLocalFileContent(res.data.content);
            setLocalFileContentFormat(res.data.format || "text");
          }
        } else if (path && selectedEntity?.source_id) {
          // Code aus einer eigenständigen Git-Wissensquelle liegt im
          // source-spezifischen Worktree. Referenzsprünge tragen die Ziel-
          // Entity (und damit source_id), aber nicht zwingend ein klassisches
          // Project.repo_id. Ohne diesen Zweig blieb der Editor nach einem
          // Sprung aus dem Referenzen-Menü leer.
          const res = await api.getKnowledgeSourceContent(selectedEntity.source_id, path);
          setLocalFileContent(res.data.content);
          setLocalFileContentFormat(res.data.format || "text");
        } else if (path && selectedProject?.repo_id) {
          // selectedProject.repo_id ist die KnowledgeSource-id der Git-Quelle
          // (siehe serialize_project) -- es gibt keinen eigenen
          // "/repositories/.../file-content"-Endpunkt, siehe handleFileSelect
          // in app/page.tsx für denselben Fix.
          const res = await api.getKnowledgeSourceContent(selectedProject.repo_id, path);
          setLocalFileContent(res.data.content);
          setLocalFileContentFormat(res.data.format || "text");
        }
      } catch (err) {
        console.error("Failed to load file content inside panel:", err);
      } finally {
        setLocalIsLoadingFile(false);
      }
    };

    loadContent();
    // Only selectedEntity's source_id actually affects which content gets
    // fetched (see the branch above) — depending on the whole entity object
    // meant picking a *different* code object in the *same* file (a new
    // object reference, same source_id) re-fetched the file from scratch.
  }, [selectedFile, selectedDoc, selectedEntity?.source_id, selectedProject, activeRightTab, theme]);

  // Local references loading effect — the "Referenzen" dropdown that consumes this
  // only exists on code/doc panels, so don't fetch it for graph/webview panels.
  useEffect(() => {
    const wantsReferences = activeRightTab === 'code' || activeRightTab === 'doc';
    const loadRefs = async () => {
      if (!wantsReferences || !selectedFile || !selectedProject) {
        setLocalFileReferences([]);
        return;
      }
      setLocalIsLoadingReferences(true);
      try {
        const res = await api.getProjectReferences(selectedProject.id, selectedFile);
        setLocalFileReferences(res.data || []);
      } catch (err) {
        console.error("Failed to load file references inside panel:", err);
      } finally {
        setLocalIsLoadingReferences(false);
      }
    };
    loadRefs();
  }, [selectedFile, selectedProject, activeRightTab]);

  const selectedLineDecorationsRef = useRef<string[]>([]);
  const selectedLineClearTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Local scroll-to-line effect
  useEffect(() => {
    if (activeEditorRef.current && selectedLine) {
      const timer = setTimeout(() => {
        const editor = activeEditorRef.current;
        if (editor) {
          editor.revealLineInCenter(selectedLine);
          editor.setPosition({ lineNumber: selectedLine, column: 1 });
          if (editor.deltaDecorations) {
            const range = {
              startLineNumber: selectedLine,
              startColumn: 1,
              endLineNumber: selectedLine,
              endColumn: 100
            };
            // Clear any highlight left over from a previous click before adding
            // the new one — reusing the prior decoration IDs (instead of `[]`)
            // is what makes this a *replace*. Without it, clicking another
            // object before the old highlight's 4s auto-clear fires stacks a
            // fresh translucent overlay on top of the still-present one, and
            // a few clicks in quick succession compound into an opaque block
            // that hides the line's text.
            selectedLineDecorationsRef.current = editor.deltaDecorations(
              selectedLineDecorationsRef.current,
              [
                {
                  range: range,
                  options: {
                    isWholeLine: true,
                    className: 'bg-ds-indigo-500/20 border-y border-ds-indigo-500/30'
                  }
                }
              ]
            );
            if (selectedLineClearTimeoutRef.current) {
              clearTimeout(selectedLineClearTimeoutRef.current);
            }
            selectedLineClearTimeoutRef.current = setTimeout(() => {
              if (activeEditorRef.current) {
                selectedLineDecorationsRef.current = activeEditorRef.current.deltaDecorations(
                  selectedLineDecorationsRef.current,
                  []
                );
              }
            }, 4000);
          }
        }
      }, 150);
      return () => clearTimeout(timer);
    }
  }, [selectedLine, selectedFile, activeEditorRef]);

  const handleReferenceItemClick = async (refItem: any) => {
    setFocusedRefNode(refItem);
    setIsLoadingFocusedRefRefs(true);
    try {
      const res = await api.getProjectReferences(selectedProject.id, refItem.file_path);
      setFocusedRefReferences(res.data || []);
    } catch (err) {
      console.error("Failed to load references for focused node:", err);
      setFocusedRefReferences([]);
    } finally {
      setIsLoadingFocusedRefRefs(false);
    }
  };

  const rulerRef = useRef<HTMLDivElement>(null);
  const monacoRef = useRef<any>(null);
  const handleEntitySelectRef = useRef(handleEntitySelect);
  const onGutterClickRef = useRef(onGutterClick);
  const onGutterAskEntityRef = useRef(onGutterAskEntity);
  const projectEntitiesRef = useRef(projectEntities);
  const selectedFileRef = useRef(selectedFile);

  // Popover opened by clicking the gutter (glyph icon / line number): lets the
  // user pick whether to pin the clicked line or the enclosing code object as
  // chat context, instead of guessing which one they meant.
  const [gutterMenu, setGutterMenu] = useState<{
    x: number;
    y: number;
    lineNumber: number;
    lineContent: string;
    entity: any | null;
  } | null>(null);
  const gutterMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    onGutterClickRef.current = onGutterClick;
  }, [onGutterClick]);

  useEffect(() => {
    onGutterAskEntityRef.current = onGutterAskEntity;
  }, [onGutterAskEntity]);

  useEffect(() => {
    handleEntitySelectRef.current = handleEntitySelect;
  }, [handleEntitySelect]);

  useEffect(() => {
    if (!gutterMenu) return;
    const handlePointerDown = (ev: MouseEvent) => {
      if (gutterMenuRef.current && !gutterMenuRef.current.contains(ev.target as Node)) {
        setGutterMenu(null);
      }
    };
    const handleKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') setGutterMenu(null);
    };
    // Attach on the next tick: the mousedown that just opened this menu is
    // still working its way through Monaco's own event handling when this
    // effect runs, and reaches `document` regardless — attaching synchronously
    // here would let it immediately close the menu it just opened.
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handlePointerDown);
      document.addEventListener('keydown', handleKeyDown);
    }, 0);
    return () => {
      clearTimeout(timer);
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [gutterMenu]);

  useEffect(() => {
    projectEntitiesRef.current = projectEntities;
  }, [projectEntities]);

  useEffect(() => {
    selectedFileRef.current = selectedFile;
  }, [selectedFile]);

  const entityDecorationsRef = useRef<string[]>([]);
  // Bumped from handleEditorDidMountLocal so the decoration effect below also
  // re-runs once the (async-mounting) Monaco editor/ref actually becomes
  // available — selectedFile/projectEntities alone can settle before mount
  // finishes, in which case the effect used to bail out once and never retry.
  const [editorMountTick, setEditorMountTick] = useState(0);

  useEffect(() => {
    const editor = activeEditorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco || !selectedFile || !projectEntities) return;

    const fileEntities = projectEntities.filter((ent: any) => ent.file_path === selectedFile);
    const model = editor.getModel();
    if (!model) return;

    const newDecorations: any[] = [];
    // Entities usually carry a stable id, but selections coming from places
    // that only pass a lightweight { file_path, start_line, name } shape
    // (e.g. search results) don't — fall back to that triple so the focused
    // object still gets recognized as "selected" instead of silently
    // matching nothing.
    const selectedKey = selectedEntity
      ? (selectedEntity.id ?? `${selectedEntity.file_path}:${selectedEntity.start_line}:${selectedEntity.name}`)
      : null;

    fileEntities.forEach((ent: any) => {
      const lineNum = ent.start_line;
      if (!lineNum || lineNum > model.getLineCount()) return;

      const lineContent = model.getLineContent(lineNum);
      const nameIndex = lineContent.toLowerCase().indexOf(ent.name.toLowerCase());

      let startCol = 1;
      let endCol = lineContent.length + 1;

      if (nameIndex !== -1) {
        startCol = nameIndex + 1;
        endCol = startCol + ent.name.length;
      }

      const entKey = ent.id ?? `${ent.file_path}:${ent.start_line}:${ent.name}`;
      const isSelected = selectedKey !== null && entKey === selectedKey;

      // The currently focused object gets its own persistent style (solid
      // fill + whole-line wash) instead of the plain dashed-underline used
      // for merely-clickable entities — otherwise, once the 4s scroll-flash
      // fades, there's no lasting cue for which object is actually selected.
      if (isSelected) {
        newDecorations.push({
          range: new monaco.Range(lineNum, 1, lineNum, 1),
          options: {
            isWholeLine: true,
            className: 'doctus-selected-entity-line'
          }
        });
      }

      newDecorations.push({
        range: new monaco.Range(lineNum, startCol, lineNum, endCol),
        options: {
          inlineClassName: isSelected ? 'doctus-selected-entity' : 'doctus-clickable-entity',
          hoverMessage: {
            value: `**${ent.name}** (${ent.type})\n\n${t('splitPane.clickToSelectReferences')}`
          },
          glyphMarginClassName: 'doctus-entity-glyph-margin',
          glyphMarginHoverMessage: {
            value: t('splitPane.codeObjectHover', { name: ent.name, type: ent.type })
          }
        }
      });
    });

    entityDecorationsRef.current = editor.deltaDecorations(
      entityDecorationsRef.current,
      newDecorations
    );

    return () => {
      // Use the editor captured when this effect ran, not a fresh read of
      // activeEditorRef.current — the active editor may have already changed
      // by the time this cleanup runs.
      if (editor && entityDecorationsRef.current.length > 0) {
        try {
          editor.deltaDecorations(entityDecorationsRef.current, []);
        } catch (e) {
          // Ignore
        }
        entityDecorationsRef.current = [];
      }
    };
  }, [selectedFile, contentToUse, projectEntities, activeEditorRef, editorMountTick, t, selectedEntity]);

  const handleEditorDidMountLocal = (editor: any, monaco: any) => {
    // Assign through the concrete ref rather than the `editorRef || localEditorRef`
    // merge (activeEditorRef) — the merge isn't statically provable as a ref by
    // the compiler, which then treats writing through it as mutating a plain value.
    if (editorRef) {
      editorRef.current = editor;
    } else {
      localEditorRef.current = editor;
    }
    monacoRef.current = monaco;
    // activeEditorRef.current is a ref mutation — doesn't retrigger the entity
    // decoration effect above by itself, hence the explicit state bump here.
    setEditorMountTick((tick) => tick + 1);

    // Register COBOL language in Monaco
    if (monaco && monaco.languages && !monaco.languages.getLanguages().some(lang => lang.id === 'cobol')) {
      monaco.languages.register({ id: 'cobol' });
      monaco.languages.setMonarchTokensProvider('cobol', {
        ignoreCase: true,
        defaultToken: '',
        keywords: [
          'ACCEPT', 'ADD', 'ALTER', 'AND', 'ARE', 'AREA', 'AREAS', 'ASCENDING', 'ASSIGN', 'AUTHOR',
          'BEFORE', 'BY', 'CALL', 'CANCEL', 'CD', 'CF', 'CH', 'CHARACTER', 'CHARACTERS', 'CLASS',
          'CLOCK-UNITS', 'CLOSE', 'COBOL', 'CODE', 'CODE-SET', 'COLLATING', 'COLUMN', 'COMMA',
          'COMMUNICATION', 'COMP', 'COMP-1', 'COMP-2', 'COMP-3', 'COMP-4', 'COMP-5', 'COMPUTATIONAL',
          'COMPUTATIONAL-1', 'COMPUTATIONAL-2', 'COMPUTATIONAL-3', 'COMPUTATIONAL-4', 'COMPUTATIONAL-5',
          'COMPUTE', 'CONFIGURATION', 'CONTAINS', 'CONTENT', 'CONTINUE', 'CONTROL', 'CONTROLS',
          'COPY', 'CORR', 'CORRESPONDING', 'COUNT', 'CURRENCY', 'DATA', 'DATE', 'DATE-COMPILED',
          'DATE-WRITTEN', 'DAY', 'DAY-OF-WEEK', 'DE', 'DEBUG-CONTENTS', 'DEBUG-ITEM', 'DEBUG-LINE',
          'DEBUG-NAME', 'DEBUG-SUB-1', 'DEBUG-SUB-2', 'DEBUG-SUB-3', 'DEBUGGING', 'DECIMAL-POINT',
          'DECLARATIVES', 'DELETE', 'DELIMITED', 'DELIMITER', 'DEPENDING', 'DESCENDING', 'DESTINATION',
          'DETAIL', 'DISABLE', 'DISPLAY', 'DIVIDE', 'DIVISION', 'DOWN', 'DUPLICATES', 'DYNAMIC',
          'EGI', 'ELSE', 'EMI', 'ENABLE', 'END', 'END-ADD', 'END-CALL', 'END-COMPUTE', 'END-DELETE',
          'END-DIVIDE', 'END-EVALUATE', 'END-IF', 'END-MULTIPLY', 'END-OF-PAGE', 'END-PERFORM',
          'END-READ', 'END-RECEIVE', 'END-RETURN', 'END-REWRITE', 'END-SEARCH', 'END-START',
          'END-STRING', 'END-SUBTRACT', 'END-UNSTRING', 'END-WRITE', 'ENTER', 'ENVIRONMENT', 'EOP',
          'EQUAL', 'ERROR', 'ESI', 'EVALUATE', 'EVERY', 'EXCEPTION', 'EXIT', 'EXTEND', 'FD', 'FILE',
          'FILE-CONTROL', 'FILLER', 'FINAL', 'FIRST', 'FOOTING', 'FOR', 'FROM', 'GENERATE', 'GIVING',
          'GLOBAL', 'GO', 'GOBACK', 'GREATER', 'GROUP', 'HEADING', 'HIGH-VALUE', 'HIGH-VALUES',
          'I-O', 'I-O-CONTROL', 'IDENTIFICATION', 'IF', 'IN', 'INDEX', 'INDEXED', 'INDICATE',
          'INITIAL', 'INITIALIZE', 'INITIATE', 'INPUT', 'INPUT-OUTPUT', 'INSPECT', 'INSTALLATION',
          'INTO', 'INVALID', 'IS', 'JUST', 'JUSTIFIED', 'KEY', 'LABEL', 'LAST', 'LEADING', 'LEFT',
          'LENGTH', 'LESS', 'LIMIT', 'LIMITS', 'LINAGE', 'LINAGE-COUNTER', 'LINE', 'LINE-COUNTER',
          'LINES', 'LINKAGE', 'LOCK', 'LOW-VALUE', 'LOW-VALUES', 'MEMORY', 'MERGE', 'MESSAGE',
          'MODE', 'MODULES', 'MOVE', 'MULTIPLE', 'MULTIPLY', 'NATIVE', 'NEGATIVE', 'NEXT', 'NO',
          'NOT', 'NUMBER', 'NUMERIC', 'NUMERIC-EDITED', 'OBJECT-COMPUTER', 'OCCURS', 'OF', 'OFF',
          'OMITTED', 'ON', 'OPEN', 'OPTIONAL', 'OR', 'ORDER', 'ORGANIZATION', 'OTHER', 'OUTPUT',
          'OVERFLOW', 'PACKED-DECIMAL', 'PAGE', 'PAGE-COUNTER', 'PERFORM', 'PF', 'PH', 'PIC',
          'PICTURE', 'PLUS', 'POINTER', 'POSITION', 'POSITIVE', 'PRINTING', 'PROCEDURE', 'PROCEDURES',
          'PROCEED', 'PROGRAM', 'PROGRAM-ID', 'QUEUE', 'QUOTE', 'QUOTES', 'RANDOM', 'RD', 'READ',
          'RECEIVE', 'RECORD', 'RECORDS', 'REDEFINES', 'REEL', 'REFERENCE', 'REFERENCES', 'RELATIVE',
          'RELEASE', 'RELOAD', 'REMAINDER', 'REMOVAL', 'RENAMES', 'REPLACE', 'REPLACING', 'REPORT',
          'REPORTING', 'REPORTS', 'RERUN', 'RESERVE', 'RESET', 'RETURN', 'RETURN-CODE', 'RETURNING',
          'REVERSED', 'REWIND', 'REWRITE', 'RF', 'RH', 'RIGHT', 'ROUNDED', 'RUN', 'SAME', 'SD',
          'SEARCH', 'SECTION', 'SECURITY', 'SEGMENT', 'SEGMENT-LIMIT', 'SELECT', 'SEND', 'SENTENCE',
          'SEPARATE', 'SEQUENCE', 'SEQUENTIAL', 'SET', 'SHARED', 'SIGN', 'SIZE', 'SORT', 'SORT-MERGE',
          'SOURCE', 'SOURCE-COMPUTER', 'SPACE', 'SPACES', 'SPECIAL-NAMES', 'STANDARD', 'STANDARD-1',
          'STANDARD-2', 'START', 'STATUS', 'STOP', 'STRING', 'SUB-QUEUE-1', 'SUB-QUEUE-2',
          'SUB-QUEUE-3', 'SUB-SUBTRACT', 'SUBTRACT', 'SUM', 'SUPPRESS', 'SYMBOLIC', 'SYNC',
          'SYNCHRONIZED', 'TABLE', 'TALLYING', 'TAPE', 'TERMINAL', 'TERMINATE', 'TEST', 'TEXT', 'THAN',
          'THEN', 'THROUGH', 'THRU', 'TIME', 'TIMES', 'TO', 'TOP', 'TRACKS', 'TRANSACTION', 'TRANSFER',
          'TRUE', 'TYPE', 'UNIT', 'UNSTRING', 'UNTIL', 'UP', 'UPON', 'USAGE', 'USE', 'USING', 'VALUE',
          'VALUES', 'VARYING', 'WHEN', 'WITH', 'WORDS', 'WORKING-STORAGE', 'WRITE', 'ZERO', 'ZEROES',
          'ZEROS'
        ],
        tokenizer: {
          root: [
            [/^.{6}[*\/].*$/, 'comment'],
            [/\*>.*/, 'comment'],
            [/(IDENTIFICATION|ENVIRONMENT|DATA|PROCEDURE)\s+DIVISION\b/, 'keyword.division'],
            [/(FILE|WORKING-STORAGE|LOCAL-STORAGE|LINKAGE|SCREEN|INPUT-OUTPUT|CONFIGURATION)\s+SECTION\b/, 'keyword.section'],
            [/[a-zA-Z\-]+/, {
              cases: {
                '@keywords': 'keyword',
                '@default': 'identifier'
              }
            }],
            [/"([^"\\]|\\.)*$/, 'string.invalid'],
            [/'([^'\\]|\\.)*$/, 'string.invalid'],
            [/"/, 'string', '@stringDouble'],
            [/'/, 'string', '@stringSingle'],
            [/\d*\.\d+([eE][\-+]?\d+)?/, 'number.float'],
            [/\d+/, 'number'],
          ],
          stringDouble: [
            [/[^"\\]+/, 'string'],
            [/\\./, 'string.escape'],
            [/"/, 'string', '@pop']
          ],
          stringSingle: [
            [/[^'\\]+/, 'string'],
            [/\\./, 'string.escape'],
            [/'/, 'string', '@pop']
          ]
        }
      });
    }

    let hoveredLineDecorations: string[] = [];

    editor.onMouseMove((e: any) => {
      const position = e.target.position;
      const lineNumber = position?.lineNumber;
      if (lineNumber) {
        hoveredLineDecorations = editor.deltaDecorations(hoveredLineDecorations, [
          {
            range: new monaco.Range(lineNumber, 1, lineNumber, 1),
            options: {
              glyphMarginClassName: 'doctus-ask-glyph-margin',
              glyphMarginHoverMessage: { value: t('splitPane.askDoctusAi') }
            }
          }
        ]);
      } else {
        hoveredLineDecorations = editor.deltaDecorations(hoveredLineDecorations, []);
      }
    });

    editor.onMouseLeave(() => {
      hoveredLineDecorations = editor.deltaDecorations(hoveredLineDecorations, []);
    });

    editor.onDidChangeModel(() => {
      hoveredLineDecorations = [];
    });

    editor.onDidScrollChange((e: any) => {
      if (e.scrollLeft !== undefined && rulerRef.current) {
        rulerRef.current.style.transform = `translateX(-${e.scrollLeft}px)`;
      }
      // Monaco fires this on any layout recompute, not just real scrolling
      // (e.g. right after opening the gutter menu below) — only close the
      // menu when the scroll offset actually moved, or it never gets a
      // chance to stay open.
      if (e.scrollTopChanged || e.scrollLeftChanged) {
        setGutterMenu(null);
      }
    });

    editor.onDidChangeCursorPosition((e: any) => {
      setCursorColumn(e.position.column);
    });

    editor.onDidChangeModelContent(() => {
      if (rulerRef.current) {
        rulerRef.current.style.transform = `translateX(0px)`;
      }
    });

    editor.onMouseDown((e: any) => {
      const position = e.target.position;
      if (!position) return;

      const lineNumber = position.lineNumber;
      const column = position.column;

      const fileEntities = (projectEntitiesRef.current || []).filter(
        (ent: any) => ent.file_path === selectedFileRef.current
      );

      // Gutter click detection: type 2 (glyph margin), type 3 (line numbers), type 4 (line decorations)
      const isGutterClick = e.target.type === 2 || e.target.type === 3 || e.target.type === 4;

      // Clicking the entity's own name text jumps straight to it — but only
      // for genuine text/content clicks. Gutter clicks report a column too
      // (often 1), which would otherwise spuriously "hit" any entity whose
      // name starts at column 1 (common for un-indented COBOL paragraphs/
      // sections) and hijack the gutter menu below.
      if (!isGutterClick) {
        const clickedEntity = fileEntities.find((ent: any) => {
          if (ent.start_line !== lineNumber) return false;

          const model = editor.getModel();
          if (!model) return false;

          const lineContent = model.getLineContent(lineNumber);
          const nameIndex = lineContent.toLowerCase().indexOf(ent.name.toLowerCase());
          if (nameIndex === -1) {
            return true;
          }

          const startCol = nameIndex + 1;
          const endCol = startCol + ent.name.length;
          return column >= startCol && column <= endCol;
        });

        if (clickedEntity) {
          if (handleEntitySelectRef.current) {
            handleEntitySelectRef.current(clickedEntity);
          }
          return;
        }
      }

      if (isGutterClick) {
        // Smallest enclosing entity (paragraph/section/program …) wins — it's
        // the most specific "code object" for this line.
        const enclosingEntity = fileEntities
          .filter((ent: any) => ent.start_line <= lineNumber && ent.end_line >= lineNumber)
          .sort((a: any, b: any) => (a.end_line - a.start_line) - (b.end_line - b.start_line))[0] || null;
        const native = e.event?.browserEvent;
        setGutterMenu({
          x: native?.clientX ?? e.event?.posx ?? 0,
          y: native?.clientY ?? e.event?.posy ?? 0,
          lineNumber,
          lineContent: editor.getModel()?.getLineContent(lineNumber) || '',
          entity: enclosingEntity,
        });
      }
    });
  };

  const exportNeo4j = async () => {
    const params = new URLSearchParams({ status: 'approved' });
    if (selectedProject?.id) params.set('project_id', String(selectedProject.id));
    const res = await fetch(`${API_URL}/graph/export/neo4j?${params}`);
    const data = await res.json();
    const blob = new Blob([data.cypher], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `knowledge_graph_${selectedProject?.name ?? 'all'}.cypher`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
    <AnimatePresence>
      {(selectedFile || selectedDoc || activeRightTab === 'graph') && (
        <div className={cn(
          "h-full border-l flex flex-col transition-all duration-300 ease-in-out bg-ds-zinc-950",
          splitClasses.editor,
          theme === 'dark' ? "border-ds-zinc-800/80 bg-ds-zinc-950" : "border-ds-zinc-200 bg-ds-white"
        )}>
          {/* Graph View — full pane when activeRightTab === 'graph' */}
          {activeRightTab === 'graph' && (
            <div className="flex-1 min-w-0 min-h-0">
              <KnowledgeGraphView
                theme={theme}
                selectedProject={selectedProject}
                selectedEntity={selectedEntity}
                selectedFile={selectedFile}
                selectedDoc={selectedDoc}
                projectEntities={projectEntities}
                onEntitySelect={handleEntitySelect}
                onFileSelect={handleFileSelect}
                onDocFocus={onDocFocus}
                layoutMode={layoutMode}
              />
            </div>
          )}

          {/* Header Editor Pane — only when NOT in graph mode */}
          {activeRightTab !== 'graph' && <div className={cn(
            "px-5 py-3 flex items-center justify-between transition-colors",
            theme === 'dark' ? "bg-ds-zinc-900/30" : "bg-ds-zinc-50/80"
          )}>
            <div className={cn(
              "flex items-center gap-1.5 text-xs font-mono text-ds-zinc-500 min-w-0 overflow-hidden transition-all duration-350",
              isEditorMaximized ? "pl-14" : "pl-0"
            )}>
              {/* Back button + breadcrumb when navigating through history */}
              {fileNavStack.length > 0 && onNavigateBack && (
                <>
                  <button
                    onClick={onNavigateBack}
                    className={cn(
                      "flex items-center gap-0.5 h-6 px-1.5 rounded-md border text-[10px] font-semibold shrink-0 transition-colors",
                      theme === 'dark'
                        ? "border-ds-zinc-700 text-ds-zinc-400 hover:text-ds-zinc-100 hover:bg-ds-zinc-800"
                        : "border-ds-zinc-300 text-ds-zinc-500 hover:text-ds-zinc-900 hover:bg-ds-zinc-100"
                    )}
                    title={t('splitPane.backToPreviousFileTitle')}
                  >
                    <ChevronLeft className="w-3 h-3" />
                    <span>{t('splitPane.back')}</span>
                  </button>
                  <div className="flex items-center gap-1 min-w-0 overflow-hidden">
                    {fileNavStack.map((entry, i) => {
                      const name = entry.file
                        ? entry.file.split('/').pop()
                        : (entry.doc?.name?.split('/').pop() || t('splitPane.docFallback'));
                      return (
                        <React.Fragment key={i}>
                          <span
                            className="text-ds-zinc-600 shrink-0 max-w-[70px] truncate"
                            title={entry.file || entry.doc?.name}
                          >
                            {name}
                          </span>
                          <ChevronRight className="w-3 h-3 text-ds-zinc-700 shrink-0" />
                        </React.Fragment>
                      );
                    })}
                  </div>
                </>
              )}
              {activeRightTab === 'code' ? (
                <Terminal className="w-4 h-4 text-ds-blue-500 shrink-0" />
              ) : activeRightTab === 'weborigin' ? (
                <Globe className="w-4 h-4 text-ds-emerald-500 shrink-0" />
              ) : (
                <BookOpen className="w-4 h-4 text-ds-orange-500 shrink-0" />
              )}
              <span
                className={cn("truncate font-semibold", theme === 'dark' ? "text-ds-zinc-300" : "text-ds-zinc-700")}
                title={activeRightTab === 'code' ? selectedFile || '' : (selectedDoc?.name || '')}
              >
                {activeRightTab === 'code'
                  ? (fileNavStack.length > 0 ? selectedFile?.split('/').pop() : selectedFile)
                  : (selectedDoc?.name?.split('/').pop() || selectedDoc?.name || t('splitPane.documentFallback'))}
              </span>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              {activeRightTab === 'weborigin' && selectedDoc?.url && (
                <a
                  href={selectedDoc.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-ds-indigo-400 hover:text-ds-indigo-300 font-semibold text-xs mr-2 transition-colors"
                >
                  <span>{t('splitPane.openInBrowser')}</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}

              {/* References Dropdown */}
              <div className="relative shrink-0">
                {(activeRightTab === 'code' || activeRightTab === 'doc') && (
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
                    title={t('splitPane.referencesPanelTitle')}
                  >
                    <Link2 className="w-3 h-3 text-ds-indigo-400" />
                    <span className="text-[9px] text-ds-zinc-500 hidden sm:inline">{t('splitPane.references')}</span>
                    {referenceBadgeCount > 0 && (
                      <span className={cn(
                        "px-1 py-0.2 text-[8px] font-bold rounded-sm leading-none",
                        theme === 'dark' ? "bg-ds-indigo-500/20 text-ds-indigo-300" : "bg-ds-indigo-100 text-ds-indigo-700"
                      )}>
                        {referenceBadgeCount}
                      </span>
                    )}
                  </button>
                )}

                {isReferencesDropdownOpen && (
                  <>
                    {/* Mobile Backdrop/Overlay & Desktop Modal Backdrop */}
                    <div
                      className={cn(
                        "fixed inset-0 bg-ds-black/60 backdrop-blur-sm z-[999]",
                        !isReferencesModalMode && "sm:hidden"
                      )}
                      onClick={() => {
                        setIsReferencesDropdownOpen(false);
                        setIsReferencesModalMode(false);
                      }}
                    />

                    <div className={cn(
                      // Mobile: Centered Modal
                      "fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[90vw] max-h-[80vh] z-[1000] sm:z-[1000]",
                      // Desktop: Dropdown or Modal
                      isReferencesModalMode
                        ? "sm:w-[70vw] sm:max-h-[85vh] sm:fixed sm:top-1/2 sm:left-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2"
                        : "sm:absolute sm:top-auto sm:left-auto sm:right-0 sm:translate-x-0 sm:translate-y-0 sm:mt-2 sm:w-96 sm:max-h-[450px]",
                      "overflow-y-auto rounded-lg border shadow-2xl flex flex-col transition-all duration-300",
                      theme === 'dark'
                        ? "bg-ds-zinc-950 border-ds-zinc-800 text-ds-zinc-300 shadow-ds-black/80"
                        : "bg-ds-white border-ds-zinc-200 text-ds-zinc-800 shadow-ds-zinc-200"
                    )}>
                    {/* Header */}
                    <div className={cn(
                      "px-4 py-3 border-b text-[10px] font-bold uppercase tracking-wider shrink-0 flex items-center justify-between",
                      theme === 'dark' ? "border-ds-zinc-800 text-ds-zinc-400" : "border-ds-zinc-200 text-ds-zinc-550"
                    )}>
                      <div className="flex items-center gap-1.5">
                        <Layers className="w-3.5 h-3.5 text-ds-indigo-500" />
                        <span>{t('splitPane.docCodeReferencesHeading')}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {!isReferencesModalMode && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setIsReferencesModalMode(true);
                            }}
                            className="hover:text-ds-indigo-400 transition-colors hidden sm:block"
                            title={t('splitPane.openAsDialogTitle')}
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <button
                          onClick={() => {
                            setIsReferencesDropdownOpen(false);
                            setIsReferencesModalMode(false);
                          }}
                          className="hover:text-ds-red-400 transition-colors"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    {/* Unified References List */}
                    <div className={cn(
                      "flex-1 overflow-y-auto",
                      isReferencesModalMode ? "sm:max-h-[70vh]" : "max-h-[350px]"
                    )}>
                      {activeRightTab === 'code' && !selectedEntity ? (
                        <div className="p-8 text-center text-xs text-ds-zinc-500 italic flex flex-col items-center gap-2">
                          <Layers className="w-8 h-8 text-ds-zinc-650 opacity-50" />
                          <span>{t('splitPane.noParsedFocusObject')}</span>
                        </div>
                      ) : activeRightTab === 'code' && isLoadingEntityNeighbors ? (
                        <div className="p-8 flex flex-col items-center justify-center gap-2.5 text-xs text-ds-zinc-500">
                          <Loader2 className="w-5 h-5 animate-spin text-ds-indigo-500" />
                          <span>{t('splitPane.loadingReferences')}</span>
                        </div>
                      ) : activeRightTab === 'code' ? (
                        Object.keys(entityNeighborGroups).length === 0 ? (
                          <div className="p-8 text-center text-xs text-ds-zinc-500 italic flex flex-col items-center gap-2">
                            <Layers className="w-8 h-8 text-ds-zinc-650 opacity-50" />
                            <span>{t('splitPane.noDirectReferencesFor', { name: selectedEntity.name })}</span>
                          </div>
                        ) : (
                          <div className="py-2">
                            {Object.entries(entityNeighborGroups).map(([group, neighbors]) => (
                              <section key={group} aria-labelledby={`neighbor-group-${group}`}>
                                <h3
                                  id={`neighbor-group-${group}`}
                                  className="px-4 pt-3 pb-1 text-[10px] font-bold uppercase tracking-wider text-ds-zinc-500"
                                >
                                  {neighborGroupLabels[group] || group.replace(':', ' · ')}
                                </h3>
                                {neighbors.map((neighbor: any) => {
                                  const entity = neighbor.entity;
                                  const document = neighbor.document;
                                  const canOpen = !!entity || !!document?.file_path;
                                  return (
                                    <button
                                      key={neighbor.edge_id}
                                      className={cn(
                                        "w-full px-4 py-2.5 text-left flex items-center gap-2 transition-colors",
                                        theme === 'dark' ? "hover:bg-ds-zinc-900/60" : "hover:bg-ds-zinc-50"
                                      )}
                                      disabled={!canOpen}
                                      onClick={() => {
                                        if (entity) {
                                          handleFileSelect(entity.file_path, entity.start_line, entity.source_id);
                                        } else if (document?.file_path) {
                                          // This panel is pinned to the code/doc view (activeRightTab is a fixed
                                          // prop here, see page.tsx renderPanel) — routing a document through the
                                          // generic handleFileSelect would also null out the global selectedEntity,
                                          // which every open callgraph panel unconditionally mirrors (see page.tsx's
                                          // unfrozen-panel sync) and would blank to "Bitte zuerst fokussieren".
                                          // onDocFocus (same mechanism the Graph View uses to open a document from
                                          // its own pinned panel) opens/targets a 'doc' panel without touching it.
                                          if (onDocFocus && document.source_id) {
                                            onDocFocus(document.file_path, document.source_id);
                                          } else {
                                            handleFileSelect(document.file_path, null, selectedEntity?.source_id);
                                          }
                                        }
                                        setIsReferencesDropdownOpen(false);
                                      }}
                                    >
                                      {document ? (
                                        <BookOpen className="w-4 h-4 text-ds-emerald-400 shrink-0" />
                                      ) : (
                                        <FileCode className="w-4 h-4 text-ds-indigo-400 shrink-0" />
                                      )}
                                      <span className="min-w-0 flex-1">
                                        <span className="block truncate text-xs font-semibold font-mono">
                                          {entity?.name || document?.title || neighbor.dst_name}
                                        </span>
                                        <span className="block truncate text-[10px] text-ds-zinc-500 font-mono">
                                          {entity?.file_path || document?.source_type || document?.file_path || t('splitPane.unresolvedLabel')}
                                        </span>
                                      </span>
                                      {entity?.start_line && (
                                        <span className="text-[9px] text-ds-zinc-500 font-mono">L{entity.start_line}</span>
                                      )}
                                    </button>
                                  );
                                })}
                              </section>
                            ))}
                          </div>
                        )
                      ) : isLoadingRefsToUse ? (
                        <div className="p-8 flex flex-col items-center justify-center gap-2.5 text-xs text-ds-zinc-500">
                          <Loader2 className="w-5 h-5 animate-spin text-ds-indigo-500" />
                          <span>{t('splitPane.searchingCodeReferences') || "Suche Referenzen..."}</span>
                        </div>
                      ) : referencesToUse.length === 0 ? (
                        <div className="p-8 text-center text-xs text-ds-zinc-500 italic flex flex-col items-center gap-2">
                          <Layers className="w-8 h-8 text-ds-zinc-650 opacity-50" />
                          <span>{t('splitPane.noCodeReferences') || "Keine Referenzen vorhanden"}</span>
                        </div>
                      ) : (
                        <div className={cn("divide-y", theme === 'dark' ? "divide-zinc-900 border-ds-zinc-900" : "divide-zinc-200")}>
                          {referencesToUse.map((ref, idx) => {
                            const isEntity = ref.node_type === 'entity';
                            const parts = (ref.file_path || "").split('/');
                            const filename = parts.pop();
                            const folderPath = parts.join('/');

                            return (
                              <button
                                key={idx}
                                id={`ref-item-${idx}`}
                                className={cn(
                                  "w-full text-left px-4 py-3 text-xs flex flex-col gap-2 transition-colors cursor-pointer block",
                                  theme === 'dark'
                                    ? "hover:bg-ds-zinc-900/50 text-ds-zinc-300"
                                    : "hover:bg-ds-zinc-50 text-ds-zinc-800"
                                )}
                                onClick={() => handleReferenceItemClick(ref)}
                              >
                                <div className="flex items-start justify-between gap-2">
                                  <div className="flex items-center gap-2 overflow-hidden">
                                    {isEntity ? (
                                      <FileCode className="w-4 h-4 text-ds-indigo-400 shrink-0" />
                                    ) : (
                                      <BookOpen className="w-4 h-4 text-ds-emerald-400 shrink-0" />
                                    )}
                                    <div className="flex flex-col truncate">
                                      <span className={cn(
                                        "font-semibold font-mono",
                                        theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-800"
                                      )}>
                                        {ref.name || ref.title}
                                      </span>
                                      {folderPath && (
                                        <span className="text-[10px] text-ds-zinc-500 font-mono truncate">
                                          {folderPath}/
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                  <span className={cn(
                                    "px-2 py-0.5 text-[9px] font-bold rounded font-mono shrink-0 border uppercase tracking-wider",
                                    ref.line
                                      ? (theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-400" : "bg-ds-zinc-100 border-ds-zinc-200 text-ds-zinc-605")
                                      : (theme === 'dark' ? "bg-ds-emerald-500/10 border-ds-emerald-500/20 text-ds-emerald-400" : "bg-ds-emerald-50 border-ds-emerald-200 text-ds-emerald-700")
                                  )}>
                                    {ref.line ? t('splitPane.lineLabel', { line: ref.line }) : (ref.source || "Document")}
                                  </span>
                                </div>

                                {ref.preview && (
                                  <div className={cn(
                                    "p-2 rounded-lg font-mono text-[10px] border-l-2 transition-colors overflow-x-auto w-full",
                                    theme === 'dark'
                                      ? "bg-ds-zinc-900/80 border-ds-indigo-500 text-ds-zinc-350"
                                      : "bg-ds-zinc-50 border-ds-indigo-600 text-ds-zinc-600"
                                  )}>
                                    <pre className="whitespace-pre overflow-x-auto select-none">
                                      {ref.preview}
                                    </pre>
                                  </div>
                                )}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    {/* Detailed Drilldown Dialog for Clicked Reference Item */}
                    {focusedRefNode && (
                      <div className="fixed inset-0 bg-ds-black/70 backdrop-blur-sm z-[2000] flex items-center justify-center p-4 animate-in fade-in duration-200">
                        <div className={cn(
                          "w-full max-w-3xl max-h-[80vh] rounded-lg border shadow-2xl flex flex-col overflow-hidden animate-in zoom-in-95 duration-200",
                          theme === 'dark' ? "bg-ds-zinc-950 border-ds-zinc-800 text-ds-zinc-300 shadow-ds-black" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-800 shadow-ds-zinc-300"
                        )}>
                          {/* Header */}
                          <div className={cn(
                            "px-4 py-3 border-b flex items-center justify-between font-semibold shrink-0 text-sm",
                            theme === 'dark' ? "border-ds-zinc-800" : "border-ds-zinc-200"
                          )}>
                            <div className="flex items-center gap-2">
                              <Layers className="w-4 h-4 text-ds-indigo-500 animate-pulse" />
                              <span>{t('splitPane.referencesForPrefix')} <strong className="font-mono text-ds-indigo-400">{focusedRefNode.name || focusedRefNode.title}</strong></span>
                            </div>
                            <button
                              onClick={() => setFocusedRefNode(null)}
                              className="p-1 rounded-lg hover:bg-ds-zinc-800/20 text-ds-zinc-550 hover:text-ds-zinc-300 transition-colors"
                            >
                              <X className="w-4.5 h-4.5" />
                            </button>
                          </div>

                          {/* Body */}
                          <div className="flex-1 overflow-y-auto p-4 space-y-3">
                            {isLoadingFocusedRefRefs ? (
                              <div className="p-12 flex flex-col items-center justify-center gap-3 text-xs text-ds-zinc-500">
                                <Loader2 className="w-6 h-6 animate-spin text-ds-indigo-500" />
                                <span>{t('splitPane.loadingLinkedReferences')}</span>
                              </div>
                            ) : focusedRefReferences.length === 0 ? (
                              <div className="p-12 text-center text-xs text-ds-zinc-500 italic flex flex-col items-center gap-2">
                                <Layers className="w-8 h-8 text-ds-zinc-650 opacity-40" />
                                <span>{t('splitPane.noDirectLinksInGraph')}</span>
                              </div>
                            ) : (
                              <div className="space-y-3">
                                {focusedRefReferences.map((ref, idx) => {
                                  const isEntity = ref.node_type === 'entity';

                                  return (
                                    <div
                                      key={idx}
                                      onClick={() => {
                                        if (ref.url && ref.url !== "#") {
                                          window.open(ref.url, '_blank', 'noopener,noreferrer');
                                        } else {
                                          handleFileSelect(ref.file_path, ref.line, ref.source_id);
                                        }
                                        setFocusedRefNode(null);
                                        setIsReferencesDropdownOpen(false);
                                        setIsReferencesModalMode(false);
                                      }}
                                      className={cn(
                                        "p-4 rounded-lg border text-xs flex flex-col gap-2 transition-all cursor-pointer hover:scale-[1.01] duration-150",
                                        theme === 'dark'
                                          ? "bg-ds-zinc-900/60 border-ds-zinc-805 hover:bg-ds-zinc-900 hover:border-ds-indigo-500/40"
                                          : "bg-ds-zinc-50 border-ds-zinc-200 hover:bg-ds-zinc-100 hover:border-ds-indigo-650/40"
                                      )}
                                    >
                                      <div className="flex items-start justify-between gap-2">
                                        <div className="flex items-center gap-2.5 overflow-hidden">
                                          {isEntity ? (
                                            <FileCode className="w-4 h-4 text-ds-indigo-400 shrink-0" />
                                          ) : (
                                            <BookOpen className="w-4 h-4 text-ds-emerald-400 shrink-0" />
                                          )}
                                          <div className="flex flex-col truncate">
                                            <span className={cn(
                                              "font-semibold font-mono",
                                              theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-805"
                                            )}>
                                              {ref.name || ref.title}
                                            </span>
                                            {ref.file_path && (
                                              <span className="text-[10px] text-ds-zinc-500 font-mono truncate">
                                                {ref.file_path}
                                              </span>
                                            )}
                                          </div>
                                        </div>

                                        <div className="flex items-center gap-1.5 shrink-0">
                                          {ref.line ? (
                                            <span className={cn(
                                              "px-2 py-0.5 text-[9px] font-bold rounded font-mono border uppercase tracking-wider",
                                              theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-400" : "bg-ds-zinc-100 border-ds-zinc-200 text-ds-zinc-600"
                                            )}>
                                              {t('splitPane.lineLabel', { line: ref.line })}
                                            </span>
                                          ) : (
                                            <span className={cn(
                                              "px-2 py-0.5 text-[9px] font-bold rounded border uppercase tracking-wider",
                                              theme === 'dark' ? "bg-ds-emerald-500/10 border-ds-emerald-500/20 text-ds-emerald-400" : "bg-ds-emerald-50 border-ds-emerald-200 text-ds-emerald-700"
                                            )}>
                                              {ref.source || t('splitPane.localSourceBadge')}
                                            </span>
                                          )}
                                        </div>
                                      </div>

                                      {ref.preview && (
                                        <div className={cn(
                                          "p-3 rounded-lg font-mono text-[10px] border-l-2 overflow-x-auto w-full",
                                          theme === 'dark'
                                            ? "bg-ds-zinc-950/80 border-ds-indigo-500 text-ds-zinc-350"
                                            : "bg-ds-white border-ds-indigo-650 text-ds-zinc-600"
                                        )}>
                                          {ref.preview}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </>
                )}
              </div>

            </div>
          </div>}

          {/* Editor wrapper — only when NOT in graph mode */}
          {activeRightTab !== 'graph' && <div className="flex-1 overflow-hidden relative flex flex-col">
            {isLoadingToUse ? (
              <div className={cn(
                "flex-1 flex flex-col items-center justify-center gap-3",
                theme === 'dark' ? "bg-ds-zinc-950 text-ds-zinc-400" : "bg-ds-zinc-50 text-ds-zinc-655"
              )}>
                <div className="relative">
                  <div className={cn(
                    "w-12 h-12 rounded-full border-2 animate-spin",
                    activeRightTab === 'code' ? (theme === 'dark' ? "border-ds-blue-500/20 border-t-blue-500" : "border-ds-blue-600/20 border-t-blue-600") :
                    activeRightTab === 'weborigin' ? (theme === 'dark' ? "border-ds-emerald-500/20 border-t-emerald-500" : "border-ds-emerald-600/20 border-t-emerald-600") :
                    (theme === 'dark' ? "border-ds-orange-500/20 border-t-orange-500" : "border-ds-orange-600/20 border-t-orange-600")
                  )} />
                  {activeRightTab === 'code' ? (
                    <Terminal className={cn("w-5 h-5 absolute inset-0 m-auto animate-pulse", theme === 'dark' ? "text-ds-blue-500" : "text-ds-blue-600")} />
                  ) : activeRightTab === 'weborigin' ? (
                    <Globe className={cn("w-5 h-5 absolute inset-0 m-auto animate-pulse", theme === 'dark' ? "text-ds-emerald-500" : "text-ds-emerald-600")} />
                  ) : (
                    <BookOpen className={cn("w-5 h-5 absolute inset-0 m-auto animate-pulse", theme === 'dark' ? "text-ds-orange-500" : "text-ds-orange-600")} />
                  )}
                </div>
                <div className="flex flex-col items-center gap-1">
                  <span className="text-sm font-semibold tracking-wide">
                    {activeRightTab === 'code' ? t('splitPane.loadingCodeFile') :
                     activeRightTab === 'weborigin' ? t('splitPane.loadingWebOrigin') :
                     t('splitPane.loadingDocument')}
                  </span>
                  <span className={cn(
                    "text-xs font-mono max-w-md truncate px-4",
                    theme === 'dark' ? "text-ds-zinc-550" : "text-ds-zinc-400"
                  )}>
                    {selectedDoc?.name || selectedFile}
                  </span>
                </div>
              </div>
            ) : activeRightTab === 'weborigin' && selectedDoc ? (
              <div className={cn("flex-1 overflow-hidden flex flex-col", theme === 'dark' ? "bg-ds-zinc-950" : "bg-ds-white")}>
                <div className="flex-1 overflow-hidden">
                  <iframe
                    srcDoc={contentToUse}
                    className={cn("w-full h-full border-none", theme === 'dark' ? "bg-ds-zinc-950" : "bg-ds-white")}
                    title={selectedDoc.name || t('splitPane.webPreviewFallbackTitle')}
                    sandbox="allow-popups allow-popups-to-escape-sandbox allow-scripts"
                  />
                </div>
              </div>
            ) : activeRightTab === 'doc' && selectedDoc ? (
              <div className="flex-1 overflow-hidden flex flex-col bg-ds-zinc-955">
                {selectedDoc.name.toLowerCase().endsWith('.pdf') ? (
                  <iframe
                    src={`${API_URL}/knowledge-sources/${selectedDoc.id}/raw?path=${encodeURIComponent(selectedDoc.name)}&theme=${theme}`}
                    className="w-full h-full border-none bg-ds-zinc-900"
                    title={selectedDoc.name}
                  />
                ) : formatToUse === 'image' ? (
                  <div className="flex-1 overflow-auto flex items-center justify-center p-6 bg-ds-zinc-925">
                    {/* next/image needs a build-time-known remote host, but API_URL is a
                        runtime env var so the same image works for every self-hosted
                        customer (see CLAUDE.md) — a static remotePatterns allowlist isn't
                        possible here. Not a primary-LCP image either (document viewer). */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={`${API_URL}/knowledge-sources/${selectedDoc.id}/raw?path=${encodeURIComponent(selectedDoc.name)}`}
                      alt={selectedDoc.name}
                      className="max-w-full max-h-full object-contain rounded-lg shadow-lg"
                    />
                  </div>
                ) : (
                  <div className={cn(
                    "flex-1 overflow-y-auto p-6 md:p-8 space-y-6 prose prose-invert max-w-none",
                    theme === 'dark' ? "text-ds-zinc-350" : "text-ds-zinc-800 bg-ds-white"
                  )}>
                    <div className={cn("border-b pb-4 mb-6 max-w-3xl mx-auto", theme === 'dark' ? "border-ds-zinc-800/80" : "border-ds-zinc-200")}>
                      <h1 className="text-2xl font-bold tracking-tight mb-2">
                        {selectedDoc.name}
                      </h1>
                      <div className="flex items-center gap-2 text-xs text-ds-zinc-500">
                        <span>{t('splitPane.knowledgeSourceLabel')}</span>
                        <span>•</span>
                        <span>{t('splitPane.documentViewerLabel')}</span>
                      </div>
                    </div>
                    <div className="max-w-3xl mx-auto">
                      {formatToUse === 'markdown' ? (
                        <MarkdownContent content={contentToUse} onFileClick={handleFileSelect} theme={theme} />
                      ) : formatToUse === 'html' ? (
                        <div
                          className="font-sans text-sm leading-relaxed"
                          dangerouslySetInnerHTML={{ __html: sanitizeHtml(contentToUse) }}
                        />
                      ) : (
                        <div className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
                          {contentToUse}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ) : selectedFile && (
              <>
                <div className={cn(
                  "flex items-center py-1.5 border-b select-none z-10 transition-colors duration-200 shrink-0",
                  theme === 'dark' ? "bg-ds-zinc-950 border-ds-zinc-900 text-ds-zinc-400" : "bg-ds-zinc-100 border-ds-zinc-200 text-ds-zinc-650"
                )}>
                  {/* Left spacer showing current column (C:XX) */}
                  <div
                    style={{ width: `${editorContentLeft}px` }}
                    className={cn(
                      "shrink-0 text-right pr-2 text-ds-indigo-500 font-bold border-r mr-2 text-[10px] select-none flex items-center justify-end font-mono",
                      theme === 'dark' ? "border-ds-zinc-800 text-ds-indigo-400" : "border-ds-zinc-300 text-ds-indigo-650"
                    )}
                  >
                    C:{cursorColumn}
                  </div>

                  {/* Scrollable Ruler Container */}
                  <div className="flex-1 overflow-hidden">
                    <div
                      ref={rulerRef}
                      className="flex flex-col whitespace-nowrap"
                      style={{ transform: 'translateX(0px)', transition: 'none' }}
                    >
                      <div
                        className="flex leading-none font-mono tracking-normal py-0.5"
                        style={{ fontSize: editorFontSize, fontFamily: editorFontFamily }}
                      >
                        {RULER_COLUMNS.map(c => {
                          const isCobol = detectLanguage(selectedFile) === 'cobol';
                          const numStr = String(cursorColumn);
                          const cursorStart = cursorColumn;
                          const cursorEnd = cursorColumn + numStr.length - 1;
                          const isCurrent = c >= cursorStart && c <= cursorEnd;

                          // Determine the character to display
                          const val = isCurrent ? numStr[c - cursorStart] : "*";

                          // Determine COBOL zone colors if isCobol
                          let zoneBg = "";
                          let zoneText = "";
                          if (isCobol) {
                            if (c >= 1 && c <= 6) {
                              zoneBg = theme === 'dark' ? "bg-ds-zinc-900/40" : "bg-ds-zinc-200/60";
                              zoneText = "text-ds-zinc-500";
                            } else if (c === 7) {
                              zoneBg = theme === 'dark' ? "bg-ds-amber-500/20" : "bg-ds-amber-500/30";
                              zoneText = "text-ds-amber-500 font-bold dark:text-ds-amber-400";
                            } else if (c >= 8 && c <= 11) {
                              zoneBg = theme === 'dark' ? "bg-ds-blue-500/15" : "bg-ds-blue-500/25";
                              zoneText = "text-ds-blue-500 font-semibold dark:text-ds-blue-400";
                            } else if (c >= 12 && c <= 72) {
                              zoneBg = theme === 'dark' ? "bg-ds-emerald-500/10" : "bg-ds-emerald-500/15";
                              zoneText = "text-ds-emerald-650 dark:text-ds-emerald-400";
                            } else if (c >= 73 && c <= 80) {
                              zoneBg = theme === 'dark' ? "bg-ds-zinc-900/40" : "bg-ds-zinc-200/60";
                              zoneText = "text-ds-zinc-500";
                            } else {
                              zoneText = theme === 'dark' ? "text-ds-zinc-650" : "text-ds-zinc-400";
                            }
                          } else {
                            zoneText = theme === 'dark' ? "text-ds-zinc-550" : "text-ds-zinc-450";
                          }

                          return (
                            <span
                              key={`ruler-${c}`}
                              className={cn(
                                "inline-block text-center select-none transition-colors",
                                zoneBg,
                                zoneText,
                                isCurrent && "bg-ds-indigo-600 text-ds-white font-bold rounded-sm scale-110 shadow-sm z-10"
                              )}
                              style={{ width: '1ch' }}
                            >
                              {val}
                            </span>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  {/* Zone Badge */}
                  <div className={cn(
                    "shrink-0 flex items-center px-3 border-l ml-2",
                    theme === 'dark' ? "border-ds-zinc-800" : "border-ds-zinc-300"
                  )}>
                    <span className={cn(
                      "text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded",
                      detectLanguage(selectedFile) === 'cobol'
                        ? (
                            cursorColumn >= 1 && cursorColumn <= 6 ? (theme === 'dark' ? "bg-ds-zinc-800 text-ds-zinc-300" : "bg-ds-zinc-700 text-ds-white") :
                            cursorColumn === 7 ? (theme === 'dark' ? "bg-ds-amber-500/20 text-ds-amber-400" : "bg-ds-amber-500 text-ds-white shadow-sm") :
                            cursorColumn >= 8 && cursorColumn <= 11 ? (theme === 'dark' ? "bg-ds-blue-500/20 text-ds-blue-400" : "bg-ds-blue-600 text-ds-white shadow-sm") :
                            cursorColumn >= 12 && cursorColumn <= 72 ? (theme === 'dark' ? "bg-ds-emerald-500/20 text-ds-emerald-400" : "bg-ds-emerald-600 text-ds-white shadow-sm") :
                            (theme === 'dark' ? "bg-ds-zinc-800 text-ds-zinc-300" : "bg-ds-zinc-700 text-ds-white")
                          )
                        : (theme === 'dark' ? "bg-ds-zinc-800 text-ds-zinc-300" : "bg-ds-zinc-700 text-ds-white")
                    )}>
                      {detectLanguage(selectedFile) === 'cobol' ? (
                        cursorColumn >= 1 && cursorColumn <= 6 ? "Sequence (1-6)" :
                        cursorColumn === 7 ? "Indicator (7)" :
                        cursorColumn >= 8 && cursorColumn <= 11 ? "Area A (8-11)" :
                        cursorColumn >= 12 && cursorColumn <= 72 ? "Area B (12-72)" :
                        "Program ID (73-80)"
                      ) : (
                        `Col: ${cursorColumn}`
                      )}
                    </span>
                  </div>
                </div>
                <Editor
                  theme={theme === 'dark' ? "vs-dark" : "light"}
                  onMount={handleEditorDidMountLocal}
                  loading={
                    <div className="absolute inset-0 flex items-center justify-center bg-ds-zinc-950 text-ds-zinc-500 text-xs gap-2">
                      <Loader2 className="w-4 h-4 animate-spin text-ds-indigo-500" />
                      {t('splitPane.editorLoading')}
                    </div>
                  }
                  defaultLanguage={detectLanguage(selectedFile)}
                  value={contentToUse}
                  options={{
                    glyphMargin: true,
                    fontSize: editorFontSize,
                    fontFamily: editorFontFamily,
                    minimap: { enabled: editorMinimap },
                    scrollBeyondLastLine: false,
                    lineNumbers: 'on',
                    padding: { top: 16, bottom: 16 },
                    readOnly: true,
                    domReadOnly: true,
                    cursorBlinking: 'smooth',
                    cursorSmoothCaretAnimation: 'on',
                    renderLineHighlight: 'all',
                    // Keine vertikalen Spaltenlinien im Code: Das kompakte
                    // COBOL-Lineal oberhalb des Editors zeigt die Zonen bereits,
                    // fünf zusätzliche Monaco-Ruler liefen durch den Quelltext.
                    rulers: [],
                    scrollbar: {
                      vertical: 'visible',
                      horizontal: 'auto',
                      verticalScrollbarSize: 8,
                      horizontalScrollbarSize: 8,
                    },
                    roundedSelection: true,
                  }}
                />
              </>
            )}
          </div>}
        </div>
      )}
    </AnimatePresence>
    {gutterMenu && typeof document !== 'undefined' && createPortal(
      <div
        ref={gutterMenuRef}
        style={{ position: 'fixed', left: gutterMenu.x + 10, top: gutterMenu.y - 8, zIndex: 10000 }}
        className={cn(
          "min-w-[220px] rounded-[3px] text-xs shadow-lg border py-1 overflow-hidden",
          theme === 'dark' ? "bg-ds-zinc-900 text-ds-zinc-300 border-ds-zinc-700 shadow-ds-black" : "bg-ds-white text-ds-zinc-800 border-ds-zinc-200 shadow-ds-zinc-300"
        )}
      >
        <button
          onClick={() => {
            onGutterClickRef.current?.(gutterMenu.lineNumber, gutterMenu.lineContent);
            setGutterMenu(null);
          }}
          className={cn(
            "w-full text-left px-2.5 py-1.5 flex items-center gap-2 transition-colors",
            theme === 'dark' ? "hover:bg-ds-zinc-800" : "hover:bg-ds-zinc-100"
          )}
        >
          <Sparkles className="w-3.5 h-3.5 text-ds-emerald-400 shrink-0" />
          <span className="truncate">{t('splitPane.askAboutLineMenuItem', { line: gutterMenu.lineNumber })}</span>
        </button>
        {gutterMenu.entity && (
          <button
            onClick={() => {
              onGutterAskEntityRef.current?.(gutterMenu.entity);
              setGutterMenu(null);
            }}
            className={cn(
              "w-full text-left px-2.5 py-1.5 flex items-center gap-2 transition-colors",
              theme === 'dark' ? "hover:bg-ds-zinc-800" : "hover:bg-ds-zinc-100"
            )}
          >
            <Layers className="w-3.5 h-3.5 text-ds-indigo-400 shrink-0" />
            <span className="truncate">{t('splitPane.askAboutEntityMenuItem', { name: gutterMenu.entity.name })}</span>
          </button>
        )}
      </div>,
      document.body
    )}
    </>
  );
};
