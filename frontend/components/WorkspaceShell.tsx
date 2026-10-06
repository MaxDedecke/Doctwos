import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { WorkspaceDocument } from '@/types/domain';
import { Code, MessageSquare, Network } from 'lucide-react';
import React from 'react';

type MobileTab = 'chat' | 'editor' | 'graph';
type LayoutMode = '1-pane' | 'split' | '3-col' | '4-grid';

interface WorkspaceShellProps {
  theme: string;
  t: (key: string, values?: Record<string, string | number>) => string;
  isMobile: boolean;
  selectedFile: string | null;
  selectedDoc: WorkspaceDocument | null;
  activeRightTab: 'code' | 'doc' | 'weborigin' | 'graph';
  setActiveRightTab: (tab: 'code' | 'doc' | 'weborigin' | 'graph') => void;
  activeMobileTab: MobileTab;
  setActiveMobileTab: (tab: MobileTab) => void;
  panelConfigs: string[];
  panelIds?: string[];
  layoutMode: LayoutMode;
  splitPercent: number;
  gridColumnPercent: number;
  gridRowPercent: number;
  isDragging: boolean;
  /** Projektfarbe (Hex/CSS); ohne Projekt gilt das Markenblau. */
  accentColor?: string | null;
  splitContainerRef: React.RefObject<HTMLDivElement>;
  threeColLeftPercent: number;
  threeColRightPercent: number;
  handleDividerMouseDown: (event: React.PointerEvent) => void;
  handleGridResizePointerDown: (event: React.PointerEvent) => void;
  handleThreeColLeftDividerPointerDown: (event: React.PointerEvent) => void;
  handleThreeColRightDividerPointerDown: (event: React.PointerEvent) => void;
  cellCls: (expanded: string) => string;
  renderPanel: (index: number) => React.ReactNode;
}

/** Akzentfarbe der Trennleisten: Projektfarbe, im Allgemein-Kontext das Markenblau. */
const DEFAULT_ACCENT = 'rgb(var(--ds-accent))';
const tint = (color: string, percent: number) => `color-mix(in srgb, ${color} ${percent}%, transparent)`;

/** Draggable divider between two workspace panels; shared by the split and 3-col layouts. */
function WorkspaceDivider({ onPointerDown, isDragging, accent }: { onPointerDown: (event: React.PointerEvent) => void; isDragging: boolean; accent: string }) {
  const [hovered, setHovered] = React.useState(false);
  const active = isDragging || hovered;
  return (
    <div
      onPointerDown={onPointerDown}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      className="hidden md:flex w-1 shrink-0 cursor-col-resize items-center justify-center group z-20 relative touch-none"
    >
      <div
        className="absolute inset-y-0 -left-1 -right-1 transition-colors"
        style={{ backgroundColor: isDragging ? tint(accent, 20) : hovered ? tint(accent, 10) : 'transparent' }}
      />
      <div
        className={cn('w-0.5 h-10 rounded-full transition-colors relative z-10', !active && 'bg-ds-zinc-700')}
        style={active ? { backgroundColor: isDragging ? accent : tint(accent, 70) } : undefined}
      />
    </div>
  );
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
  panelIds,
  layoutMode,
  splitPercent,
  gridColumnPercent,
  gridRowPercent,
  isDragging,
  accentColor,
  splitContainerRef,
  threeColLeftPercent,
  threeColRightPercent,
  handleDividerMouseDown,
  handleGridResizePointerDown,
  handleThreeColLeftDividerPointerDown,
  handleThreeColRightDividerPointerDown,
  cellCls,
  renderPanel,
}: WorkspaceShellProps) {
  const accent = accentColor || DEFAULT_ACCENT;
  const [knobHovered, setKnobHovered] = React.useState(false);
  const gridStyle = layoutMode === '4-grid'
    ? {
        // Subtract half the gap from each track so the two percentages fill
        // the available area without adding the gap on top of 100 percent.
        gridTemplateColumns: `minmax(0, calc(${gridColumnPercent}% - 0.25rem)) minmax(0, calc(${100 - gridColumnPercent}% - 0.25rem))`,
        gridTemplateRows: `minmax(0, calc(${gridRowPercent}% - 0.25rem)) minmax(0, calc(${100 - gridRowPercent}% - 0.25rem))`,
      }
    : undefined;

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
          <div className="flex-1 p-2 h-full overflow-hidden">
            <div className={cn('h-full w-full', layoutMode === '4-grid' ? 'relative grid gap-2' : cn('flex', layoutMode !== '1-pane' && 'gap-2'))} style={gridStyle}>
            {panelConfigs.map((_, index) => (
              <React.Fragment key={panelIds?.[index] ?? `panel-${index}`}>
                {layoutMode === 'split' && index === 1 && (
                  <WorkspaceDivider onPointerDown={handleDividerMouseDown} isDragging={isDragging} accent={accent} />
                )}
                {layoutMode === '3-col' && (index === 1 || index === 2) && (
                  <WorkspaceDivider
                    onPointerDown={index === 1 ? handleThreeColLeftDividerPointerDown : handleThreeColRightDividerPointerDown}
                    isDragging={isDragging}
                    accent={accent}
                  />
                )}
                {layoutMode === 'split' && index === 0 ? (
                  <div style={{ width: `${splitPercent}%` }} className={cn('h-full flex flex-col min-w-0', !isDragging && 'transition-all duration-300')}>
                    {renderPanel(0)}
                  </div>
                ) : layoutMode === '3-col' && index === 0 ? (
                  <div style={{ width: `${threeColLeftPercent}%` }} className={cn('h-full flex flex-col min-w-0', !isDragging && 'transition-all duration-300')}>
                    {renderPanel(0)}
                  </div>
                ) : layoutMode === '3-col' && index === 1 ? (
                  <div style={{ width: `${threeColRightPercent - threeColLeftPercent}%` }} className={cn('h-full flex flex-col min-w-0', !isDragging && 'transition-all duration-300')}>
                    {renderPanel(1)}
                  </div>
                ) : (
                  <div className={cellCls('flex-1')}>{renderPanel(index)}</div>
                )}
              </React.Fragment>
            ))}
            {layoutMode === '4-grid' && (
              <button
                type="button"
                onPointerDown={handleGridResizePointerDown}
                aria-label={t('page.workspace.resizeGrid')}
                title={t('page.workspace.resizeGrid')}
                className="absolute z-30 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 cursor-move touch-none items-center justify-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ds-indigo-500"
                style={{
                  left: `${gridColumnPercent}%`,
                  top: `${gridRowPercent}%`,
                  backgroundColor: isDragging ? tint(accent, 25) : knobHovered ? tint(accent, 15) : undefined,
                }}
                onPointerEnter={() => setKnobHovered(true)}
                onPointerLeave={() => setKnobHovered(false)}
              >
                <span className={cn('absolute h-0.5 w-7 rounded-full', !isDragging && 'bg-ds-zinc-600')} style={isDragging ? { backgroundColor: accent } : undefined} />
                <span className={cn('absolute h-7 w-0.5 rounded-full', !isDragging && 'bg-ds-zinc-600')} style={isDragging ? { backgroundColor: accent } : undefined} />
                <span className="relative h-2 w-2 rounded-full" style={{ backgroundColor: accent }} />
              </button>
            )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
