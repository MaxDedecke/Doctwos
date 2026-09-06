/**
 * O-056: `Sidebar.tsx` hatte nach dem O-036-Umbau nur für die ausgelagerten
 * Unterkomponenten (`VirtualizedSessionList`, `FileTreeList`,
 * `sidebarFileTree`) Tests -- die in der Sidebar selbst verbliebene
 * Orchestrierung war ungetestet. Diese Datei deckt genau diese vier Bereiche
 * ab: Ordner-Akkordeon (`expandedFolderId` inkl. Nachladen/Cache der
 * Dateiliste), Filterung der gepinnten Quellen nach Projektkontext,
 * Sidebar-Resize und das Schließen der Sidebar bei einer Auswahl auf
 * Mobilbreite.
 *
 * Beide Listen der Sidebar rendern gefenstert (@tanstack/react-virtual) und
 * messen dafür `offsetHeight`, das jsdom mangels Layout immer als 0 meldet --
 * ohne den Spy unten hielte der Virtualizer den Container für 0px hoch und
 * würde keine einzige Zeile rendern (gleiches Vorgehen wie in
 * `sidebar/VirtualizedSessionList.test.tsx`).
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { Sidebar } from './Sidebar';
import { api } from '@/app/services/api';

vi.mock('@/app/services/api', () => ({
  api: {
    getKnowledgeSourceFiles: vi.fn(),
  },
}));

const DESKTOP_WIDTH = 1280;
const MOBILE_WIDTH = 500;

function setWindowWidth(width: number) {
  Object.defineProperty(window, 'innerWidth', { value: width, configurable: true, writable: true });
}

function makeProps(overrides: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  return {
    theme: 'dark',
    isSidebarOpen: true,
    setIsSidebarOpen: vi.fn(),
    backendStatus: 'online',
    startNewChat: vi.fn(),
    sessions: [] as any[],
    activeSessionId: null,
    handleSessionSelect: vi.fn(),
    handleRemoveSession: vi.fn(),
    selectedProject: null,
    selectedFile: null,
    selectedDoc: null,
    handleFileSelect: vi.fn(),
    handleLogout: vi.fn(),
    connectedSources: [] as any[],
    pinnedSourceIds: [] as number[],
    currentUser: null,
    ...overrides,
  };
}

function renderSidebar(overrides: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  const props = makeProps(overrides);
  const view = render(
    <LanguageProvider>
      <Sidebar {...(props as any)} />
    </LanguageProvider>
  );
  return { ...view, props };
}

/** Der Zähler steht im jeweiligen Abschnitts-Kopf neben der Überschrift. */
function sectionCount(headline: string): string {
  const header = screen.getByText(headline).closest('div')!;
  return within(header).getByText(/^\d+$/).textContent!;
}

function filesResponse(files: string[]) {
  return { data: { files } } as any;
}

describe('Sidebar', () => {
  let offsetHeightSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    setWindowWidth(DESKTOP_WIDTH);
    offsetHeightSpy = vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(300);
    vi.mocked(api.getKnowledgeSourceFiles).mockResolvedValue(filesResponse([]));
  });

  afterEach(() => {
    offsetHeightSpy.mockRestore();
    vi.clearAllMocks();
  });

  it('rendert im geschlossenen Zustand keinen Inhalt', () => {
    renderSidebar({ isSidebarOpen: false });

    expect(document.getElementById('sidebar-new-chat-btn')).toBeNull();
    expect(screen.queryByText('Verlauf')).toBeNull();
  });

  describe('Verlauf', () => {
    const sessions = [
      { id: 1, title: 'Globale Sitzung', project_id: null },
      { id: 2, title: 'Projekt-A-Sitzung', project_id: 10 },
      { id: 3, title: 'Projekt-B-Sitzung', project_id: 20 },
    ];

    it('zeigt ohne Projektkontext nur projektlose Sitzungen', () => {
      renderSidebar({ sessions });

      expect(screen.getByText('Globale Sitzung')).toBeTruthy();
      expect(screen.queryByText('Projekt-A-Sitzung')).toBeNull();
      expect(screen.queryByText('Projekt-B-Sitzung')).toBeNull();
      expect(sectionCount('Verlauf')).toBe('1');
    });

    it('zeigt im Projektkontext nur die Sitzungen dieses Projekts', () => {
      renderSidebar({ sessions, selectedProject: { id: 10, name: 'Projekt A' } });

      expect(screen.getByText('Projekt-A-Sitzung')).toBeTruthy();
      expect(screen.queryByText('Globale Sitzung')).toBeNull();
      expect(screen.queryByText('Projekt-B-Sitzung')).toBeNull();
      expect(sectionCount('Verlauf')).toBe('1');
    });

    it('klappt den Verlauf über die Kopfzeile ein und wieder aus', () => {
      renderSidebar({ sessions });

      fireEvent.click(screen.getByText('Verlauf'));
      expect(screen.queryByText('Globale Sitzung')).toBeNull();
      // Der Zähler bleibt auch eingeklappt sichtbar.
      expect(sectionCount('Verlauf')).toBe('1');

      fireEvent.click(screen.getByText('Verlauf'));
      expect(screen.getByText('Globale Sitzung')).toBeTruthy();
    });

    it('reicht die Auswahl einer Sitzung nach oben durch', () => {
      const { props } = renderSidebar({ sessions });

      fireEvent.click(document.getElementById('sidebar-session-item-1')!);

      expect(props.handleSessionSelect).toHaveBeenCalledWith(sessions[0]);
    });
  });

  describe('gepinnte Wissensquellen', () => {
    const sources = [
      { id: 1, name: 'Globales Repo', type: 'git', project_id: null },
      { id: 2, name: 'Projekt-A-Repo', type: 'git', project_id: 10 },
      { id: 3, name: 'Projekt-B-Repo', type: 'git', project_id: 20 },
    ];

    it('zeigt nur angepinnte Quellen', () => {
      renderSidebar({ connectedSources: sources, pinnedSourceIds: [1] });

      expect(screen.getByText('Globales Repo')).toBeTruthy();
      expect(screen.queryByText('Projekt-A-Repo')).toBeNull();
      expect(sectionCount('Wissensquellen')).toBe('1');
    });

    it('blendet ohne Projektkontext projektgebundene Quellen aus', () => {
      renderSidebar({ connectedSources: sources, pinnedSourceIds: [1, 2, 3] });

      expect(screen.getByText('Globales Repo')).toBeTruthy();
      expect(screen.queryByText('Projekt-A-Repo')).toBeNull();
      expect(screen.queryByText('Projekt-B-Repo')).toBeNull();
    });

    it('zeigt im Projektkontext die eigenen und die globalen, nicht die fremden Quellen', () => {
      renderSidebar({
        connectedSources: sources,
        pinnedSourceIds: [1, 2, 3],
        selectedProject: { id: 10, name: 'Projekt A' },
      });

      expect(screen.getByText('Projekt-A-Repo')).toBeTruthy();
      expect(screen.getByText('Globales Repo')).toBeTruthy();
      expect(screen.queryByText('Projekt-B-Repo')).toBeNull();
    });

    it('kennzeichnet eine globale Quelle im Projektkontext als "Global", außerhalb nicht', () => {
      const { unmount } = renderSidebar({
        connectedSources: sources,
        pinnedSourceIds: [1],
        selectedProject: { id: 10, name: 'Projekt A' },
      });
      expect(screen.getByText('Global')).toBeTruthy();

      unmount();

      renderSidebar({ connectedSources: sources, pinnedSourceIds: [1] });
      expect(screen.queryByText('Global')).toBeNull();
    });

    it('zeigt höchstens vier gepinnte Quellen', () => {
      const many = Array.from({ length: 6 }, (_, i) => ({
        id: i + 1,
        name: `Quelle ${i + 1}`,
        type: 'git',
        project_id: null,
      }));

      renderSidebar({ connectedSources: many, pinnedSourceIds: many.map(s => s.id) });

      expect(screen.getAllByText(/^Quelle \d$/)).toHaveLength(4);
      expect(screen.queryByText('Quelle 5')).toBeNull();
      expect(sectionCount('Wissensquellen')).toBe('4');
    });

    it('zeigt einen Hinweis, wenn nichts angepinnt ist', () => {
      renderSidebar({ connectedSources: sources, pinnedSourceIds: [] });

      expect(screen.getByText('Keine Wissensquellen angepinnt')).toBeTruthy();
      expect(sectionCount('Wissensquellen')).toBe('0');
    });
  });

  describe('Ordner-Akkordeon', () => {
    const gitSource = { id: 7, name: 'COBOL-Repo', type: 'git', project_id: null };
    const secondSource = { id: 8, name: 'Zweites Repo', type: 'git', project_id: null };
    const localSource = { id: 9, name: 'Handbuch.pdf', type: 'local', project_id: null };

    it('lädt die Dateien beim Aufklappen und zeigt sie an', async () => {
      vi.mocked(api.getKnowledgeSourceFiles).mockResolvedValue(filesResponse(['src/MAIN.cbl', 'src/SUB.cbl']));

      renderSidebar({ connectedSources: [gitSource], pinnedSourceIds: [7] });

      fireEvent.click(screen.getByText('COBOL-Repo'));

      await waitFor(() => expect(screen.getByText('MAIN.cbl')).toBeTruthy());
      expect(screen.getByText('SUB.cbl')).toBeTruthy();
      expect(api.getKnowledgeSourceFiles).toHaveBeenCalledWith(7);
    });

    it('lädt eine bereits geladene Quelle beim erneuten Aufklappen nicht noch einmal', async () => {
      vi.mocked(api.getKnowledgeSourceFiles).mockResolvedValue(filesResponse(['src/MAIN.cbl']));

      renderSidebar({ connectedSources: [gitSource], pinnedSourceIds: [7] });

      fireEvent.click(screen.getByText('COBOL-Repo'));
      await waitFor(() => expect(screen.getByText('MAIN.cbl')).toBeTruthy());

      // Zuklappen ...
      fireEvent.click(screen.getByText('COBOL-Repo'));
      expect(screen.queryByText('MAIN.cbl')).toBeNull();

      // ... und wieder auf: aus dem Cache, kein zweiter Request.
      fireEvent.click(screen.getByText('COBOL-Repo'));
      await waitFor(() => expect(screen.getByText('MAIN.cbl')).toBeTruthy());
      expect(api.getKnowledgeSourceFiles).toHaveBeenCalledTimes(1);
    });

    it('zeigt während des Ladens einen Ladehinweis', async () => {
      let resolveFiles: (value: unknown) => void = () => {};
      vi.mocked(api.getKnowledgeSourceFiles).mockReturnValue(
        new Promise(resolve => { resolveFiles = resolve; }) as any
      );

      renderSidebar({ connectedSources: [gitSource], pinnedSourceIds: [7] });

      fireEvent.click(screen.getByText('COBOL-Repo'));
      expect(screen.getByText('Dateien werden geladen...')).toBeTruthy();

      resolveFiles(filesResponse(['src/MAIN.cbl']));
      await waitFor(() => expect(screen.getByText('MAIN.cbl')).toBeTruthy());
    });

    it('zeigt einen Hinweis, wenn die Quelle keine Dateien enthält', async () => {
      vi.mocked(api.getKnowledgeSourceFiles).mockResolvedValue(filesResponse([]));

      renderSidebar({ connectedSources: [gitSource], pinnedSourceIds: [7] });

      fireEvent.click(screen.getByText('COBOL-Repo'));

      await waitFor(() => expect(screen.getByText('Keine Dateien vorhanden')).toBeTruthy());
    });

    it('hält immer nur eine Quelle gleichzeitig offen', async () => {
      vi.mocked(api.getKnowledgeSourceFiles).mockImplementation((id: number) =>
        Promise.resolve(filesResponse([id === 7 ? 'src/MAIN.cbl' : 'src/OTHER.cbl'])) as any
      );

      renderSidebar({ connectedSources: [gitSource, secondSource], pinnedSourceIds: [7, 8] });

      fireEvent.click(screen.getByText('COBOL-Repo'));
      await waitFor(() => expect(screen.getByText('MAIN.cbl')).toBeTruthy());

      fireEvent.click(screen.getByText('Zweites Repo'));
      await waitFor(() => expect(screen.getByText('OTHER.cbl')).toBeTruthy());
      expect(screen.queryByText('MAIN.cbl')).toBeNull();
    });

    it('öffnet eine lokale Quelle direkt, statt sie aufzuklappen', () => {
      const { props } = renderSidebar({ connectedSources: [localSource], pinnedSourceIds: [9] });

      fireEvent.click(screen.getByText('Handbuch.pdf'));

      expect(props.handleFileSelect).toHaveBeenCalledWith('Handbuch.pdf', undefined, '9');
      expect(api.getKnowledgeSourceFiles).not.toHaveBeenCalled();
    });

    it('überlebt einen fehlgeschlagenen Datei-Abruf ohne Absturz', async () => {
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
      vi.mocked(api.getKnowledgeSourceFiles).mockRejectedValue(new Error('network down'));

      renderSidebar({ connectedSources: [gitSource], pinnedSourceIds: [7] });

      fireEvent.click(screen.getByText('COBOL-Repo'));

      await waitFor(() => expect(screen.getByText('Keine Dateien vorhanden')).toBeTruthy());
      expect(consoleError).toHaveBeenCalled();
      consoleError.mockRestore();
    });
  });

  describe('Schließen bei Auswahl auf Mobilbreite', () => {
    const gitSource = { id: 7, name: 'COBOL-Repo', type: 'git', project_id: null };
    const sessions = [{ id: 1, title: 'Globale Sitzung', project_id: null }];

    it('schließt die Sidebar nach "Neuer Chat"', () => {
      setWindowWidth(MOBILE_WIDTH);
      const { props } = renderSidebar();

      fireEvent.click(document.getElementById('sidebar-new-chat-btn')!);

      expect(props.startNewChat).toHaveBeenCalled();
      expect(props.setIsSidebarOpen).toHaveBeenCalledWith(false);
    });

    it('lässt die Sidebar auf Desktopbreite offen', () => {
      const { props } = renderSidebar();

      fireEvent.click(document.getElementById('sidebar-new-chat-btn')!);

      expect(props.startNewChat).toHaveBeenCalled();
      expect(props.setIsSidebarOpen).not.toHaveBeenCalled();
    });

    it('schließt die Sidebar nach Auswahl einer Sitzung', () => {
      setWindowWidth(MOBILE_WIDTH);
      const { props } = renderSidebar({ sessions });

      fireEvent.click(document.getElementById('sidebar-session-item-1')!);

      expect(props.handleSessionSelect).toHaveBeenCalled();
      expect(props.setIsSidebarOpen).toHaveBeenCalledWith(false);
    });

    it('schließt die Sidebar nach Auswahl einer Datei im Baum und meldet die Quellen-ID mit', async () => {
      vi.mocked(api.getKnowledgeSourceFiles).mockResolvedValue(filesResponse(['src/MAIN.cbl']));
      setWindowWidth(MOBILE_WIDTH);
      const { props } = renderSidebar({ connectedSources: [gitSource], pinnedSourceIds: [7] });

      fireEvent.click(screen.getByText('COBOL-Repo'));
      await waitFor(() => expect(screen.getByText('MAIN.cbl')).toBeTruthy());

      fireEvent.click(screen.getByText('MAIN.cbl'));

      expect(props.handleFileSelect).toHaveBeenCalledWith('src/MAIN.cbl', undefined, '7');
      expect(props.setIsSidebarOpen).toHaveBeenCalledWith(false);
    });

    it('schließt die Sidebar nach Auswahl einer lokalen Quelle', () => {
      setWindowWidth(MOBILE_WIDTH);
      const local = { id: 9, name: 'Handbuch.pdf', type: 'local', project_id: null };
      const { props } = renderSidebar({ connectedSources: [local], pinnedSourceIds: [9] });

      fireEvent.click(screen.getByText('Handbuch.pdf'));

      expect(props.setIsSidebarOpen).toHaveBeenCalledWith(false);
    });
  });

  describe('Resize', () => {
    function panelWidth(container: HTMLElement): string {
      return (container.querySelector('aside')!.firstElementChild as HTMLElement).style.width;
    }

    function resizeHandle(container: HTMLElement): HTMLElement {
      return container.querySelector('.cursor-col-resize') as HTMLElement;
    }

    it('startet mit der Standardbreite', () => {
      const { container } = renderSidebar();

      expect(panelWidth(container)).toBe('280px');
    });

    it('übernimmt die Zeigerposition als neue Breite', () => {
      const { container } = renderSidebar();

      fireEvent.mouseDown(resizeHandle(container));
      fireEvent.mouseMove(document, { clientX: 400 });

      expect(panelWidth(container)).toBe('400px');
    });

    it('ignoriert Breiten außerhalb der Grenzen (180/500)', () => {
      const { container } = renderSidebar();

      fireEvent.mouseDown(resizeHandle(container));

      fireEvent.mouseMove(document, { clientX: 120 });
      expect(panelWidth(container)).toBe('280px');

      fireEvent.mouseMove(document, { clientX: 700 });
      expect(panelWidth(container)).toBe('280px');
    });

    it('beendet das Ziehen beim Loslassen der Maustaste', () => {
      const { container } = renderSidebar();

      fireEvent.mouseDown(resizeHandle(container));
      fireEvent.mouseMove(document, { clientX: 400 });
      fireEvent.mouseUp(document);

      fireEvent.mouseMove(document, { clientX: 460 });

      expect(panelWidth(container)).toBe('400px');
    });

    it('rendert keinen Ziehgriff, solange die Sidebar geschlossen ist', () => {
      const { container } = renderSidebar({ isSidebarOpen: false });

      expect(resizeHandle(container)).toBeNull();
    });
  });

  describe('Fußzeile', () => {
    it('zeigt Name und E-Mail des angemeldeten Nutzers', () => {
      renderSidebar({ currentUser: { name: 'Max Muster', email: 'max@example.org', role: 'admin' } });

      expect(screen.getByText('Max Muster')).toBeTruthy();
      expect(screen.getByText('max@example.org')).toBeTruthy();
    });

    it('fällt ohne Nutzerdaten auf die Standardbeschriftung zurück', () => {
      renderSidebar({ currentUser: null });

      expect(screen.getByText('Doctus Nutzer')).toBeTruthy();
      expect(screen.getByText('Lokale Sitzung')).toBeTruthy();
    });

    it('meldet den Nutzer über den Abmelde-Knopf ab', () => {
      const { props } = renderSidebar();

      fireEvent.click(document.getElementById('logout-btn')!);

      expect(props.handleLogout).toHaveBeenCalled();
    });
  });
});
