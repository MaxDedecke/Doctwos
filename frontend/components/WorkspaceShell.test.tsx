/**
 * O-057: `WorkspaceShell.tsx` hatte keinen Test -- getestet war bisher nur die
 * darunterliegende Resize-Arithmetik (`lib/workspaceResize.ts`,
 * `hooks/useWorkspaceLayout.ts`), nicht die Komponente, die daraus das
 * tatsaechliche Layout baut. Abgedeckt wird genau das, was die Komponente
 * selbst entscheidet: welches Layout je `layoutMode` entsteht, welche Teiler
 * dabei ueberhaupt gerendert werden (und welcher Handler an welchem haengt),
 * ob die aus dem Snapshot stammenden Prozentwerte als Panel-Breiten ankommen
 * und wie die Mobil-Ansicht auf genau ein Panel reduziert.
 *
 * `WorkspaceShell` ist zustandslos: Layoutmodus, Prozentwerte, Drag-Zustand,
 * `t`, `cellCls` und `renderPanel` kommen alle als Props aus `page.tsx` bzw.
 * `useWorkspaceLayout`. Die Tests brauchen deshalb keine Provider und keine
 * gemockte API -- `renderPanel` liefert hier schlicht ein markiertes Div je
 * Index, an dem sich Reihenfolge und Breiten ablesen lassen.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WorkspaceShell } from './WorkspaceShell';

function makeProps(overrides: Partial<React.ComponentProps<typeof WorkspaceShell>> = {}) {
  return {
    theme: 'dark',
    t: (key: string) => key,
    isMobile: false,
    selectedFile: null,
    selectedDoc: null,
    activeRightTab: 'code' as const,
    setActiveRightTab: vi.fn(),
    activeMobileTab: 'chat' as const,
    setActiveMobileTab: vi.fn(),
    panelConfigs: ['chat'],
    layoutMode: '1-pane' as const,
    splitPercent: 50,
    gridColumnPercent: 50,
    gridRowPercent: 50,
    isDragging: false,
    splitContainerRef: React.createRef<HTMLDivElement>(),
    threeColLeftPercent: 33,
    threeColRightPercent: 66,
    handleDividerMouseDown: vi.fn(),
    handleGridResizePointerDown: vi.fn(),
    handleThreeColLeftDividerPointerDown: vi.fn(),
    handleThreeColRightDividerPointerDown: vi.fn(),
    cellCls: (expanded: string) => `cell ${expanded}`,
    renderPanel: (index: number) => <div data-testid={`panel-${index}`}>Panel {index}</div>,
    ...overrides,
  };
}

function renderShell(overrides: Partial<React.ComponentProps<typeof WorkspaceShell>> = {}) {
  const props = makeProps(overrides);
  const view = render(<WorkspaceShell {...(props as any)} />);
  return { ...view, props };
}

/** Das Wrapper-Div, das die Komponente um das jeweilige Panel legt. */
function panelWrapper(index: number): HTMLElement {
  return screen.getByTestId(`panel-${index}`).parentElement as HTMLElement;
}

function dividers(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>('.cursor-col-resize'));
}

describe('WorkspaceShell', () => {
  describe('Layout je layoutMode', () => {
    it('1-pane: ein Panel, kein Teiler, kein Kreuzgriff', () => {
      const { container } = renderShell({ layoutMode: '1-pane', panelConfigs: ['chat'] });

      expect(screen.getByTestId('panel-0')).toBeTruthy();
      expect(screen.queryByTestId('panel-1')).toBeNull();
      expect(dividers(container)).toHaveLength(0);
      expect(screen.queryByLabelText('page.workspace.resizeGrid')).toBeNull();
      // Ohne Gap, weil es nichts zu trennen gibt.
      expect(panelWrapper(0).parentElement!.className).not.toContain('gap-2');
    });

    it('split: zwei Panels mit genau einem Teiler dazwischen', () => {
      const { container } = renderShell({ layoutMode: 'split', panelConfigs: ['chat', 'code'] });

      expect(screen.getByTestId('panel-0')).toBeTruthy();
      expect(screen.getByTestId('panel-1')).toBeTruthy();

      const found = dividers(container);
      expect(found).toHaveLength(1);
      // Der Teiler steht zwischen den beiden Panels, nicht davor oder dahinter.
      expect(found[0].previousElementSibling).toBe(panelWrapper(0));
      expect(found[0].nextElementSibling).toBe(panelWrapper(1));
    });

    it('3-col: drei Panels mit zwei Teilern an den beiden Grenzen', () => {
      const { container } = renderShell({
        layoutMode: '3-col',
        panelConfigs: ['chat', 'code', 'graph'],
      });

      expect(screen.getByTestId('panel-2')).toBeTruthy();

      const found = dividers(container);
      expect(found).toHaveLength(2);
      expect(found[0].previousElementSibling).toBe(panelWrapper(0));
      expect(found[0].nextElementSibling).toBe(panelWrapper(1));
      expect(found[1].previousElementSibling).toBe(panelWrapper(1));
      expect(found[1].nextElementSibling).toBe(panelWrapper(2));
    });

    it('4-grid: vier Panels im Raster, keine Spaltenteiler, dafuer der Kreuzgriff', () => {
      const { container } = renderShell({
        layoutMode: '4-grid',
        panelConfigs: ['chat', 'code', 'graph', 'links'],
      });

      expect(screen.getByTestId('panel-3')).toBeTruthy();
      expect(dividers(container)).toHaveLength(0);
      expect(screen.getByLabelText('page.workspace.resizeGrid')).toBeTruthy();
      expect(panelWrapper(0).parentElement!.className).toContain('grid');
    });

    it('rendert fuer jeden Eintrag in panelConfigs genau ein Panel', () => {
      const renderPanel = vi.fn((index: number) => <div data-testid={`panel-${index}`}>Panel {index}</div>);
      renderShell({ layoutMode: '3-col', panelConfigs: ['chat', 'code', 'graph'], renderPanel });

      expect(renderPanel).toHaveBeenCalledTimes(3);
      expect(renderPanel.mock.calls.map(([index]) => index)).toEqual([0, 1, 2]);
    });
  });

  describe('Panel-Breiten aus dem Snapshot', () => {
    it('split: Panel 0 bekommt splitPercent, Panel 1 fuellt den Rest', () => {
      renderShell({ layoutMode: 'split', panelConfigs: ['chat', 'code'], splitPercent: 35 });

      expect(panelWrapper(0).style.width).toBe('35%');
      // Das zweite Panel hat keine feste Breite, sondern nimmt sich den Rest.
      expect(panelWrapper(1).style.width).toBe('');
      expect(panelWrapper(1).className).toContain('flex-1');
    });

    it('3-col: die beiden Grenzwerte ergeben die Breiten der ersten beiden Spalten', () => {
      renderShell({
        layoutMode: '3-col',
        panelConfigs: ['chat', 'code', 'graph'],
        threeColLeftPercent: 25,
        threeColRightPercent: 70,
      });

      expect(panelWrapper(0).style.width).toBe('25%');
      // Panel 1 liegt zwischen beiden Teilern -- also die Differenz.
      expect(panelWrapper(1).style.width).toBe('45%');
      expect(panelWrapper(2).style.width).toBe('');
      expect(panelWrapper(2).className).toContain('flex-1');
    });

    it('4-grid: Spalten- und Zeilenanteil landen im Raster und in der Griffposition', () => {
      renderShell({
        layoutMode: '4-grid',
        panelConfigs: ['chat', 'code', 'graph', 'links'],
        gridColumnPercent: 60,
        gridRowPercent: 40,
      });

      const grid = panelWrapper(0).parentElement!;
      const style = grid.getAttribute('style') || '';
      expect(style).toContain('60%');
      expect(style).toContain('40%');

      const handle = screen.getByLabelText('page.workspace.resizeGrid');
      expect(handle.style.left).toBe('60%');
      expect(handle.style.top).toBe('40%');
    });

    it('laesst die Breitenanimation waehrend des Ziehens weg', () => {
      const { unmount } = renderShell({ layoutMode: 'split', panelConfigs: ['chat', 'code'], isDragging: false });
      expect(panelWrapper(0).className).toContain('transition-all');
      unmount();

      renderShell({ layoutMode: 'split', panelConfigs: ['chat', 'code'], isDragging: true });
      expect(panelWrapper(0).className).not.toContain('transition-all');
    });
  });

  describe('Teiler-Handler', () => {
    it('split: der Teiler meldet sich beim Split-Handler', () => {
      const { container, props } = renderShell({ layoutMode: 'split', panelConfigs: ['chat', 'code'] });

      fireEvent.pointerDown(dividers(container)[0]);

      expect(props.handleDividerMouseDown).toHaveBeenCalled();
      expect(props.handleThreeColLeftDividerPointerDown).not.toHaveBeenCalled();
    });

    it('3-col: linker und rechter Teiler haengen an unterschiedlichen Handlern', () => {
      const { container, props } = renderShell({
        layoutMode: '3-col',
        panelConfigs: ['chat', 'code', 'graph'],
      });
      const [left, right] = dividers(container);

      fireEvent.pointerDown(left);
      expect(props.handleThreeColLeftDividerPointerDown).toHaveBeenCalled();
      expect(props.handleThreeColRightDividerPointerDown).not.toHaveBeenCalled();

      fireEvent.pointerDown(right);
      expect(props.handleThreeColRightDividerPointerDown).toHaveBeenCalled();
      expect(props.handleDividerMouseDown).not.toHaveBeenCalled();
    });

    it('4-grid: der Kreuzgriff meldet sich beim Raster-Handler', () => {
      const { props } = renderShell({
        layoutMode: '4-grid',
        panelConfigs: ['chat', 'code', 'graph', 'links'],
      });

      fireEvent.pointerDown(screen.getByLabelText('page.workspace.resizeGrid'));

      expect(props.handleGridResizePointerDown).toHaveBeenCalled();
    });
  });

  describe('Mobil-Umschalter', () => {
    const panels = ['chat', 'code', 'graph'];

    it('bleibt verborgen, solange weder Datei noch Dokument noch Graph offen ist', () => {
      renderShell({ panelConfigs: panels, selectedFile: null, selectedDoc: null, activeRightTab: 'code' });

      expect(screen.queryByText('page.mobileTab.chat')).toBeNull();
    });

    it('erscheint, sobald eine Datei ausgewaehlt ist', () => {
      renderShell({ panelConfigs: panels, selectedFile: 'src/MAIN.cbl' });

      expect(screen.getByText('page.mobileTab.chat')).toBeTruthy();
      expect(screen.getByText('page.mobileTab.editor')).toBeTruthy();
      expect(screen.getByText('page.mobileTab.graph')).toBeTruthy();
    });

    it('erscheint auch ohne Datei, wenn der Graph offen ist', () => {
      renderShell({ panelConfigs: panels, activeRightTab: 'graph' });

      expect(screen.getByText('page.mobileTab.chat')).toBeTruthy();
    });

    it('schaltet auf den Graph-Tab und zieht die rechte Ansicht mit', () => {
      const { props } = renderShell({ panelConfigs: panels, selectedFile: 'src/MAIN.cbl' });

      fireEvent.click(screen.getByText('page.mobileTab.graph'));

      expect(props.setActiveMobileTab).toHaveBeenCalledWith('graph');
      expect(props.setActiveRightTab).toHaveBeenCalledWith('graph');
    });

    it('holt beim Wechsel vom Graph zum Editor die Code-Ansicht zurueck', () => {
      const { props } = renderShell({
        panelConfigs: panels,
        selectedFile: 'src/MAIN.cbl',
        activeRightTab: 'graph',
      });

      fireEvent.click(screen.getByText('page.mobileTab.editor'));

      expect(props.setActiveMobileTab).toHaveBeenCalledWith('editor');
      expect(props.setActiveRightTab).toHaveBeenCalledWith('code');
    });

    it('holt beim Wechsel vom Graph zum Editor die Dokumentansicht zurueck, wenn nur ein Dokument offen ist', () => {
      const { props } = renderShell({
        panelConfigs: panels,
        selectedFile: null,
        selectedDoc: { id: 1, name: 'Handbuch.pdf' },
        activeRightTab: 'graph',
      });

      fireEvent.click(screen.getByText('page.mobileTab.editor'));

      expect(props.setActiveRightTab).toHaveBeenCalledWith('doc');
    });

    it('laesst die rechte Ansicht unangetastet, wenn der Graph gar nicht offen ist', () => {
      const { props } = renderShell({
        panelConfigs: panels,
        selectedFile: 'src/MAIN.cbl',
        activeRightTab: 'code',
      });

      fireEvent.click(screen.getByText('page.mobileTab.editor'));

      expect(props.setActiveMobileTab).toHaveBeenCalledWith('editor');
      expect(props.setActiveRightTab).not.toHaveBeenCalled();
    });
  });

  describe('Mobil-Ansicht', () => {
    const panels = ['chat', 'code', 'graph'];

    it('zeigt nur das Chat-Panel, weder Teiler noch die anderen Panels', () => {
      const { container } = renderShell({
        isMobile: true,
        layoutMode: '3-col',
        panelConfigs: panels,
        activeMobileTab: 'chat',
      });

      expect(screen.getByTestId('panel-0')).toBeTruthy();
      expect(screen.queryByTestId('panel-1')).toBeNull();
      expect(screen.queryByTestId('panel-2')).toBeNull();
      expect(dividers(container)).toHaveLength(0);
    });

    it('zeigt im Editor-Tab das erste Panel, das weder Chat noch Graph ist', () => {
      renderShell({
        isMobile: true,
        layoutMode: '3-col',
        panelConfigs: panels,
        activeMobileTab: 'editor',
      });

      expect(screen.getByTestId('panel-1')).toBeTruthy();
      expect(screen.queryByTestId('panel-0')).toBeNull();
    });

    it('zeigt im Graph-Tab das Graph-Panel, unabhaengig von seiner Position', () => {
      renderShell({
        isMobile: true,
        layoutMode: '3-col',
        panelConfigs: ['graph', 'chat', 'code'],
        activeMobileTab: 'graph',
      });

      expect(screen.getByTestId('panel-0')).toBeTruthy();
      expect(screen.queryByTestId('panel-1')).toBeNull();
    });

    it('reicht -1 durch, wenn der aktive Tab in panelConfigs gar nicht vorkommt', () => {
      const renderPanel = vi.fn((index: number) => <div data-testid={`panel-${index}`}>Panel {index}</div>);
      renderShell({
        isMobile: true,
        panelConfigs: ['chat'],
        activeMobileTab: 'graph',
        renderPanel,
      });

      // indexOf('graph') ist -1. Die Shell rechnet den Index nicht nach, sondern
      // reicht ihn unveraendert weiter -- was daraus wird, entscheidet
      // `renderPanel` in `page.tsx` (dort greift der `|| 'chat'`-Fallback).
      // Wichtig ist hier nur: es wird nicht faelschlich Panel 0 gezeigt.
      expect(renderPanel).toHaveBeenCalledWith(-1);
      expect(renderPanel).not.toHaveBeenCalledWith(0);
      expect(screen.queryByTestId('panel-0')).toBeNull();
    });
  });
});
