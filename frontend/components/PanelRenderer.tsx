import React from 'react';
import {
  BookOpen,
  Braces,
  Box,
  ChevronLeft,
  ChevronRight,
  Globe,
  Lock,
  MessageSquare,
  RefreshCw,
  Terminal,
  X,
} from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import type { PanelHistoryEntry, PanelSelection } from '@/lib/panelHistory';

type Translate = (key: string, values?: Record<string, unknown>) => string;

interface PanelRendererProps {
  index: number;
  contentType: string;
  selection: PanelSelection;
  focusObject: any | null;
  theme: string;
  t: Translate;
  selectedProject: any | null;
  panelFrozen: boolean;
  collapsed: boolean;
  panelCount: number;
  panelHistory?: PanelHistoryEntry;
  linkManagerEnabled: boolean;
  content: React.ReactNode;
  onContentTypeChange: (index: number, type: string) => void;
  onExpand: (index: number) => void;
  onMouseEnter: (index: number) => void;
  onHistoryBack: (index: number) => void;
  onHistoryForward: (index: number) => void;
  onToggleFreeze: (index: number) => void;
  onCollapse: (index: number) => void;
  onClose: (index: number) => void;
}

export function PanelRenderer({
  index,
  contentType,
  selection,
  focusObject,
  theme,
  t,
  selectedProject,
  panelFrozen,
  collapsed,
  panelCount,
  panelHistory,
  linkManagerEnabled,
  content,
  onContentTypeChange,
  onExpand,
  onMouseEnter,
  onHistoryBack,
  onHistoryForward,
  onToggleFreeze,
  onCollapse,
  onClose,
}: PanelRendererProps) {
  const isChat = contentType === 'chat';
  const focusInfo = getPanelFocusInfo(focusObject, selection, t);

  if (isChat && collapsed) {
    return (
      <button
        onClick={() => onExpand(index)}
        title={t('page.workspace.expandChat')}
        className={cn(
          'h-full w-full flex flex-col items-center gap-3 py-3 border rounded-lg transition-colors cursor-pointer group',
          theme === 'dark'
            ? 'bg-ds-zinc-950/40 border-ds-zinc-900 text-ds-zinc-400 hover:text-ds-indigo-400 hover:border-ds-zinc-800'
            : 'bg-ds-white/40 border-ds-zinc-200 text-ds-zinc-500 hover:text-ds-indigo-600 hover:border-ds-zinc-300'
        )}
      >
        <span className={cn(
          'p-1.5 rounded-lg border',
          theme === 'dark' ? 'border-ds-zinc-800 bg-ds-zinc-900/60' : 'border-ds-zinc-200 bg-ds-zinc-50'
        )}>
          <ChevronRight className="w-3.5 h-3.5" />
        </span>
        <MessageSquare className="w-4 h-4 text-ds-indigo-500 shrink-0" />
        <span className="text-[10px] font-bold uppercase tracking-widest" style={{ writingMode: 'vertical-rl' }}>
          {t('page.mobileTab.chat')}
        </span>
      </button>
    );
  }

  return (
    <div
      onMouseEnter={() => onMouseEnter(index)}
      className={cn(
        'h-full flex flex-col min-w-0 rounded-lg overflow-hidden relative group transition-all duration-300',
        panelFrozen ? 'border-2 border-ds-amber-500 shadow-[0_0_16px_rgba(245,158,11,0.55)]' : 'border',
        theme === 'dark'
          ? (panelFrozen ? 'bg-ds-zinc-955' : 'bg-ds-zinc-950/40 border-ds-zinc-900')
          : (panelFrozen ? 'bg-ds-amber-50/5' : 'bg-ds-white/40 border-ds-zinc-200')
      )}
      style={(!panelFrozen && selectedProject?.color) ? {
        boxShadow: `0 4px 20px rgba(0, 0, 0, 0.05), 0 0 15px ${selectedProject.color}${theme === 'dark' ? '12' : '08'}`,
        borderColor: `${selectedProject.color}25`,
      } : undefined}
    >
      <div className={cn(
        'px-3 py-1.5 border-b flex items-center justify-between shrink-0 z-20 backdrop-blur-md select-none transition-colors duration-300',
        theme === 'dark'
          ? (panelFrozen ? 'border-ds-amber-500/20 bg-ds-zinc-950/60' : 'border-ds-zinc-900 bg-ds-zinc-950/60')
          : (panelFrozen ? 'border-ds-amber-500/20 bg-ds-zinc-50/60' : 'border-ds-zinc-200 bg-ds-zinc-50/60')
      )}>
        <Select value={contentType} onValueChange={(type) => onContentTypeChange(index, type)}>
          <SelectTrigger aria-label={t('page.panelTypeSelectorLabel')} className={cn(
            'h-6 text-[10px] bg-transparent border-0 font-bold uppercase tracking-wider focus:ring-0 focus:ring-offset-0 px-1 py-0 gap-1.5 w-auto transition-colors duration-200',
            panelFrozen ? 'text-ds-amber-500 hover:text-ds-amber-400' : 'text-ds-indigo-400 hover:text-ds-indigo-350'
          )}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent className={theme === 'dark' ? 'bg-ds-zinc-950 border-ds-zinc-900 text-ds-zinc-100' : 'bg-ds-white border-ds-zinc-200 text-ds-zinc-900'}>
            <SelectItem value="chat" className="text-xs">{t('page.viewTypes.chat')}</SelectItem>
            <SelectItem value="code" className="text-xs">{t('page.viewTypes.code')}</SelectItem>
            <SelectItem value="doc" className="text-xs">{t('page.viewTypes.doc')}</SelectItem>
            <SelectItem value="graph" className="text-xs">{t('page.viewTypes.graph')}</SelectItem>
            <SelectItem value="callgraph" className="text-xs">{t('page.viewTypes.callgraph')}</SelectItem>
            <SelectItem value="webview" className="text-xs">{t('page.viewTypes.webview')}</SelectItem>
            {linkManagerEnabled && <SelectItem value="linkmanager" className="text-xs">{t('page.viewTypes.linkmanager')}</SelectItem>}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-1.5">
          <button onClick={() => onHistoryBack(index)} disabled={(panelHistory?.past.length || 0) === 0} className={historyButtonClass(theme)} title={`${t('page.workspace.historyBack')} (Alt+←)`}>
            <ChevronLeft className="w-3 h-3" />
          </button>
          <button onClick={() => onHistoryForward(index)} disabled={(panelHistory?.future.length || 0) === 0} className={historyButtonClass(theme)} title={`${t('page.workspace.historyForward')} (Alt+→)`}>
            <ChevronRight className="w-3 h-3" />
          </button>
          <button
            onClick={() => onToggleFreeze(index)}
            className={cn(
              'p-1 rounded border transition-all duration-150 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider cursor-pointer',
              panelFrozen
                ? 'bg-ds-amber-500/10 border-ds-amber-500/30 text-ds-amber-500 hover:bg-ds-amber-500/20'
                : (theme === 'dark' ? 'bg-transparent border-ds-zinc-800 text-ds-zinc-500 hover:text-ds-zinc-300 hover:border-ds-zinc-700' : 'bg-transparent border-ds-zinc-200 text-ds-zinc-400 hover:text-ds-zinc-700 hover:border-ds-zinc-300')
            )}
            title={panelFrozen ? t('page.workspace.freezePausedTitle') : t('page.workspace.freezeActiveTitle')}
          >
            {panelFrozen ? <><Lock className="w-3 h-3 text-ds-amber-500" /><span className="text-[9px] text-ds-amber-500 hidden sm:inline">{t('page.workspace.frozenBadge')}</span></> : <><RefreshCw className="w-3 h-3 text-ds-emerald-500 animate-[spin_8s_linear_infinite]" /><span className="text-[9px] text-ds-zinc-500 hidden sm:inline">{t('page.workspace.liveBadge')}</span></>}
          </button>
          {isChat && <button onClick={() => onCollapse(index)} className={cn('p-1 rounded border transition-all duration-150 flex items-center justify-center cursor-pointer', theme === 'dark' ? 'bg-transparent border-ds-zinc-800 text-ds-zinc-550 hover:text-ds-indigo-400 hover:border-ds-indigo-900/40 hover:bg-ds-indigo-950/20' : 'bg-transparent border-ds-zinc-200 text-ds-zinc-400 hover:text-ds-indigo-600 hover:border-ds-indigo-200 hover:bg-ds-indigo-50')} title={t('page.workspace.collapseChat')}><ChevronLeft className="w-3 h-3" /></button>}
          {panelCount > 1 && <button onClick={() => onClose(index)} className={cn('p-1 rounded border transition-all duration-150 flex items-center justify-center cursor-pointer', theme === 'dark' ? 'bg-transparent border-ds-zinc-800 text-ds-zinc-550 hover:text-ds-red-400 hover:border-ds-red-900/40 hover:bg-ds-red-950/20' : 'bg-transparent border-ds-zinc-200 text-ds-zinc-400 hover:text-ds-red-500 hover:border-ds-red-200 hover:bg-ds-red-50')} title={t('page.workspace.closeView')}><X className="w-3 h-3" /></button>}
        </div>
      </div>

      {contentType !== 'doc' && contentType !== 'webview' && contentType !== 'linkmanager' && (
        <div className={cn('px-3 py-1 border-b flex items-center gap-1.5 text-[11px] shrink-0 z-10 min-w-0', theme === 'dark' ? 'border-ds-zinc-900 bg-ds-zinc-950/40' : 'border-ds-zinc-200 bg-ds-zinc-50/40')}>
          {focusInfo ? <>
            <focusInfo.Icon className={cn('w-3 h-3 shrink-0', focusInfo.colorClass)} />
            <span className={cn('truncate font-medium', theme === 'dark' ? 'text-ds-zinc-300' : 'text-ds-zinc-700')} title={focusInfo.label}>{focusInfo.label}</span>
            <span className="text-ds-zinc-600 shrink-0">·</span>
            <span className="text-ds-zinc-500 uppercase tracking-wide text-[9px] shrink-0">{focusInfo.kind}</span>
          </> : <span className="text-ds-zinc-600 italic">{t('page.focusBar.none')}</span>}
        </div>
      )}

      <div className="flex-1 min-w-0 min-h-0 overflow-hidden relative">{content}</div>
    </div>
  );
}

function historyButtonClass(theme: string) {
  return cn(
    'p-1 rounded border transition-all duration-150 flex items-center justify-center cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent',
    theme === 'dark'
      ? 'bg-transparent border-ds-zinc-800 text-ds-zinc-500 hover:text-ds-zinc-200 hover:border-ds-zinc-700'
      : 'bg-transparent border-ds-zinc-200 text-ds-zinc-400 hover:text-ds-zinc-700 hover:border-ds-zinc-300'
  );
}

function getPanelFocusInfo(focusObject: any | null, selection: PanelSelection, t: Translate) {
  if (focusObject) return { Icon: Box, label: focusObject.name, kind: focusObject.kind || t('page.focusBar.entity'), colorClass: 'text-ds-purple-400' };
  if (selection.selectedEntity) return { Icon: Braces, label: selection.selectedEntity.name, kind: selection.selectedEntity.type || t('page.focusBar.entity'), colorClass: 'text-ds-indigo-400' };
  if (selection.selectedDoc) {
    const isWeb = selection.selectedDoc.isWebOrigin || ['confluence', 'jira'].includes((selection.selectedDoc.type || '').toLowerCase());
    return {
      Icon: isWeb ? Globe : BookOpen,
      label: isWeb ? selection.selectedDoc.name : (selection.selectedDoc.name?.split('/').pop() || selection.selectedDoc.name),
      kind: isWeb ? t('page.focusBar.webOrigin') : t('page.focusBar.document'),
      colorClass: isWeb ? 'text-ds-emerald-400' : 'text-ds-orange-400',
    };
  }
  if (selection.selectedFile) return { Icon: Terminal, label: selection.selectedFile, kind: t('page.focusBar.file'), colorClass: 'text-ds-blue-400' };
  return null;
}
