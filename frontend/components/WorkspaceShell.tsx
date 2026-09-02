import React from 'react';
import { Code, MessageSquare, Network } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

type MobileTab = 'chat' | 'editor' | 'graph';
type LayoutMode = '1-pane' | 'split' | '3-col' | '4-grid';

interface WorkspaceShellProps {
  theme: string;
  t: (key: string, values?: Record<string, unknown>) => string;
  isMobile: boolean;
  selectedFile: string | null;
  selectedDoc: any | null;
  activeRightTab: 'code' | 'doc' | 'weborigin' | 'graph';
  setActiveRightTab: (tab: 'code' | 'doc' | 'weborigin' | 'graph') => void;
  activeMobileTab: MobileTab;
  setActiveMobileTab: (tab: MobileTab) => void;
  panelConfigs: string[];
  layoutMode: LayoutMode;
  splitPercent: number;
  isDragging: boolean;
  splitContainerRef: React.RefObject<HTMLDivElement | null>;
  handleDividerMouseDown: (event: React.MouseEvent) => void;
  isPanelCollapsed: (index: number) => boolean;
  cellCls: (index: number, expanded: string) => string;
  renderPanel: (index: number) => React.ReactNode;
}

export function WorkspaceShell({
  theme,
  t,
  isMobile,
  selectedFile,
  selectedDoc,
  activeRightTab,
  setActiveRightTab,
  activeMobileTab,
  setActiveMobileTab,
  panelConfigs,
  layoutMode,
  splitPercent,
  isDragging,
  splitContainerRef,
  handleDividerMouseDown,
  isPanelCollapsed,
  cellCls,
  renderPanel,
}: WorkspaceShellProps) {
  return (
    <>
      {(selectedFile || selectedDoc || activeRightTab === 'graph') && (
        <div className={cn('flex md:hidden border-b p-2 gap-2 justify-center shrink-0 z-20', theme === 'dark' ? 'border-ds-zinc-800 bg-ds-zinc-900/40' : 'border-ds-zinc-200 bg-ds-zinc-100/50')}>
          <Button variant={activeMobileTab === 'chat' ? 'default' : 'ghost'} onClick={() => setActiveMobileTab('chat')} className={cn('flex-1 text-xs gap-1.5 h-8 rounded-lg font-bold', activeMobileTab === 'chat' && 'bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-550')}>
            <MessageSquare className="w-3.5 h-3.5" />
            <span>{t('page.mobileTab.chat')}</span>
          </Button>
          <Button variant={activeMobileTab === 'editor' ? 'default' : 'ghost'} onClick={() => {
            setActiveMobileTab('editor');
            if (activeRightTab === 'graph') {
              if (selectedFile) setActiveRightTab('code');
              else if (selectedDoc) setActiveRightTab('doc');
            }
          }} className={cn('flex-1 text-xs gap-1.5 h-8 rounded-lg font-bold', activeMobileTab === 'editor' && 'bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-550')}>
            <Code className="w-3.5 h-3.5" />
            <span>{t('page.mobileTab.editor')}</span>
          </Button>
          <Button variant={activeMobileTab === 'graph' ? 'default' : 'ghost'} onClick={() => {
            setActiveMobileTab('graph');
            setActiveRightTab('graph');
          }} className={cn('flex-1 text-xs gap-1.5 h-8 rounded-lg font-bold', activeMobileTab === 'graph' && 'bg-ds-indigo-600 text-ds-white hover:bg-ds-indigo-550')}>
            <Network className="w-3.5 h-3.5" />
            <span>{t('page.mobileTab.graph')}</span>
          </Button>
        </div>
      )}

      <div ref={splitContainerRef} className="flex-1 flex overflow-hidden z-10 mt-1">
        {isMobile ? (
          <div className="flex-1 p-2 h-full">
            {activeMobileTab === 'chat' && renderPanel(panelConfigs.indexOf('chat'))}
            {activeMobileTab === 'editor' && renderPanel(panelConfigs.findIndex((type) => type !== 'chat' && type !== 'graph'))}
            {activeMobileTab === 'graph' && renderPanel(panelConfigs.indexOf('graph'))}
          </div>
        ) : (
          <div className={cn('flex-1 p-2 h-full overflow-hidden', layoutMode === '4-grid' ? 'grid grid-cols-2 grid-rows-2 gap-2' : cn('flex', layoutMode !== '1-pane' && 'gap-2'))}>
            {panelConfigs.map((_, index) => (
              <React.Fragment key={index}>
                {layoutMode === 'split' && index === 1 && (
                  <div onMouseDown={handleDividerMouseDown} className="hidden md:flex w-1 shrink-0 cursor-col-resize items-center justify-center group z-20 relative">
                    <div className={cn('absolute inset-y-0 -left-1 -right-1', isDragging ? 'bg-ds-indigo-500/20' : 'group-hover:bg-ds-indigo-500/10')} />
                    <div className={cn('w-0.5 h-10 rounded-full transition-colors relative z-10', isDragging ? 'bg-ds-indigo-500' : 'bg-ds-zinc-700 group-hover:bg-ds-indigo-400')} />
                  </div>
                )}
                {layoutMode === 'split' && index === 0 ? (
                  <div style={isPanelCollapsed(0) ? undefined : { width: `${splitPercent}%` }} className={cn('h-full flex flex-col min-w-0', isPanelCollapsed(0) && 'flex-none w-12', !isDragging && 'transition-all duration-300')}>
                    {renderPanel(0)}
                  </div>
                ) : (
                  <div className={cellCls(index, 'flex-1')}>{renderPanel(index)}</div>
                )}
              </React.Fragment>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
