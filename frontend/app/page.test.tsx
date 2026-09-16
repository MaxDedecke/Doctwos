/**
 * O-106 — Integrationstest der Hauptseiten-Verdrahtung (`app/page.tsx`).
 *
 * Die einzelnen Bausteine (Sidebar, GlobalSearch, SettingsModal,
 * WorkspaceShell/PanelRenderer, die Daten-Hooks aus O-105, die
 * Panel-Synchronisation aus O-092) haben alle eigene Tests. Was fehlt, ist die
 * Verdrahtung darüber: page.tsx entscheidet z.B., wann ein Projekt-, Datei-
 * oder Sitzungswechsel den laufenden Chat zurücksetzt, und synchronisiert die
 * `?chat=`-URL mit der aktiven Sitzung. Genau das prüft diese Datei — die
 * schweren Blattkomponenten (Panel-Inhalt, Sidebar, GlobalSearch, LoginView,
 * SettingsModal) sind daher zu schlanken Stubs gemockt, die nur die für die
 * Orchestrierung relevanten Props/Callbacks offenlegen.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'react';
import { axiosResponse } from '@/test/http';
import { api } from '@/app/services/api';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import type { GlobalSearch } from '@/components/GlobalSearch';
import type { Sidebar } from '@/components/Sidebar';
import type { PanelContentRenderer } from '@/components/PanelContentRenderer';
import type { ChatSession, Project } from '@/types/domain';
import App from './page';

type GlobalSearchProps = ComponentProps<typeof GlobalSearch>;
type SidebarProps = ComponentProps<typeof Sidebar>;
type PanelContentRendererProps = ComponentProps<typeof PanelContentRenderer>;

const routerPush = vi.hoisted(() => vi.fn());
let searchParamsValue = new URLSearchParams();

vi.mock('next/navigation', () => ({
  usePathname: () => '/workspace',
  useRouter: () => ({ push: routerPush }),
  useSearchParams: () => searchParamsValue,
}));

vi.mock('@/app/services/api', () => ({
  api: {
    getMe: vi.fn(),
    logout: vi.fn(),
    getModelInfo: vi.fn(),
    getModels: vi.fn(),
    resolveEntity: vi.fn(),
    getProjects: vi.fn(),
    getProjectFiles: vi.fn(),
    getProjectStats: vi.fn(),
    getProjectEntities: vi.fn(),
    getKnowledgeSources: vi.fn(),
    getProjectReferences: vi.fn(),
    getChatSessions: vi.fn(),
    getChatSessionByUuid: vi.fn(),
    getChatMessages: vi.fn(),
    updateChatMessageFeedback: vi.fn(),
    getKnowledgeSourceContent: vi.fn(),
    resolveWebOrigin: vi.fn(),
    deleteChatSession: vi.fn(),
    createChatSession: vi.fn(),
    updateChatSessionSnapshot: vi.fn(),
    shareChatSession: vi.fn(),
  },
}));

// Eigene Tests: components/LoginView.test.tsx, GlobalSearch.test.tsx,
// Sidebar.test.tsx, PanelContentRenderer.test.tsx. Hier reichen Stubs, die
// die für die Orchestrierung relevanten Props sichtbar/auslösbar machen.
vi.mock('@/components/LoginView', () => ({
  LoginView: ({ onAuthenticated }: { onAuthenticated: () => void }) => (
    <div data-testid="login-view">
      <button onClick={onAuthenticated}>login</button>
    </div>
  ),
}));

vi.mock('@/components/SettingsModal', () => ({
  SettingsModal: ({ isOpen }: { isOpen: boolean }) => (
    <div data-testid="settings-modal">{isOpen ? 'open' : 'closed'}</div>
  ),
}));

vi.mock('@/components/GlobalSearch', () => ({
  GlobalSearch: (props: GlobalSearchProps) => (
    <div data-testid="global-search">
      <span data-testid="search-selected-project">{props.selectedProject?.name ?? 'none'}</span>
      {props.projects.map((p) => (
        <button key={p.id} onClick={() => props.onProjectSelect(p)}>{`select-project-${p.id}`}</button>
      ))}
      <button onClick={() => props.onProjectSelect(null)}>select-no-project</button>
      <button onClick={props.onOpenGraphView}>open-graph</button>
      <button onClick={() => props.onSelectResult({
        node_type: 'document',
        node_id: 501,
        node_label: 'HANDBUCH.md',
        node_url: null,
        node_meta: { file_path: 'HANDBUCH.md', project_id: 2 },
      })}
      >
        select-document-result
      </button>
      <button onClick={() => props.onSelectResult({
        node_type: 'entity',
        node_id: 101,
        node_label: 'PaymentService',
        node_url: null,
        node_meta: {
          project_id: 2,
          source_id: 55,
          file_path: 'src/main/java/com/acme/PaymentService.java',
          start_line: 8,
          type: 'class',
        },
      })}>
        select-java-entity-result
      </button>
    </div>
  ),
}));

vi.mock('@/components/Sidebar', () => ({
  Sidebar: (props: SidebarProps) => (
    <div data-testid="sidebar">
      <span data-testid="sidebar-selected-project">{props.selectedProject?.name ?? 'none'}</span>
      <span data-testid="sidebar-active-session">{props.activeSessionId ?? 'none'}</span>
      <span data-testid="sidebar-backend-status">{props.backendStatus}</span>
      <button onClick={props.startNewChat}>start-new-chat</button>
      <button onClick={props.handleLogout}>logout</button>
      {props.sessions.map((s) => (
        <button key={s.id} onClick={() => props.handleSessionSelect(s)}>{`select-session-${s.id}`}</button>
      ))}
      <button onClick={() => props.handleFileSelect('ACCOUNT.cbl', 12)}>sidebar-select-file</button>
    </div>
  ),
}));

vi.mock('@/components/PanelContentRenderer', () => ({
  PanelContentRenderer: (props: PanelContentRendererProps) => (
    <div data-testid={`panel-content-${props.index}`}>
      <span data-testid={`panel-type-${props.index}`}>{props.contentType}</span>
      <span data-testid={`panel-project-${props.index}`}>{props.selectedProject?.name ?? 'none'}</span>
      <span data-testid={`panel-messages-${props.index}`}>{props.chatMessages.length}</span>
    </div>
  ),
}));

const mockedApi = vi.mocked(api);

function project(overrides: Partial<Project> = {}): Project {
  return { id: 1, name: 'Kontoführung', status: 'completed', repo_id: 55, ...overrides };
}
const projectA = project();
const projectB = project({ id: 2, name: 'Zinsberechnung' });

function chatSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return { id: 7, uuid: 'chat-7', title: 'Alte Frage', project_id: 1, ...overrides };
}

function renderApp() {
  return render(
    <LanguageProvider>
      <App />
    </LanguageProvider>,
  );
}

describe('app/page.tsx — Orchestrierung', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    routerPush.mockReset();
    searchParamsValue = new URLSearchParams();
    mockedApi.getMe.mockResolvedValue(axiosResponse({ id: 1, username: 'max', is_admin: true }));
    mockedApi.logout.mockResolvedValue(axiosResponse({}));
    mockedApi.getModelInfo.mockResolvedValue(axiosResponse({ llm: 'mistral-nemo', embedding: 'bge-m3' }));
    mockedApi.getModels.mockResolvedValue(axiosResponse({ models: ['mistral-nemo'] }));
    mockedApi.resolveEntity.mockRejectedValue({ isAxiosError: true, response: { status: 404 } });
    mockedApi.getProjects.mockResolvedValue(axiosResponse([]));
    mockedApi.getProjectFiles.mockResolvedValue(axiosResponse([]));
    mockedApi.getProjectStats.mockResolvedValue(axiosResponse({ total_files: 0, total_lines: 0, languages: [] }));
    mockedApi.getProjectEntities.mockResolvedValue(axiosResponse([]));
    mockedApi.getKnowledgeSources.mockResolvedValue(axiosResponse([]));
    mockedApi.getProjectReferences.mockResolvedValue(axiosResponse([]));
    mockedApi.getChatSessions.mockResolvedValue(axiosResponse([]));
    mockedApi.getChatMessages.mockResolvedValue(axiosResponse([]));
    mockedApi.getKnowledgeSourceContent.mockResolvedValue(axiosResponse({ content: 'code', format: 'text' }));
    mockedApi.updateChatSessionSnapshot.mockResolvedValue(axiosResponse({}));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows a loading spinner before the login check resolves, then the login view once unauthenticated', async () => {
    let rejectGetMe!: (error: unknown) => void;
    mockedApi.getMe.mockReturnValue(new Promise((_resolve, reject) => { rejectGetMe = reject; }));
    renderApp();

    expect(screen.getByText('Doctus wird geladen...')).toBeTruthy();

    await act(async () => { rejectGetMe(new Error('not logged in')); });

    expect(await screen.findByTestId('login-view')).toBeTruthy();
  });

  it('loads the workspace and its project/source/session data once login succeeds', async () => {
    mockedApi.getProjects.mockResolvedValue(axiosResponse([projectA]));
    renderApp();

    await screen.findByTestId('sidebar');

    expect(mockedApi.getProjects).toHaveBeenCalledTimes(1);
    expect(mockedApi.getKnowledgeSources).toHaveBeenCalledTimes(1);
    expect(mockedApi.getChatSessions).toHaveBeenCalledTimes(1);
  });

  it('returns to the login view on logout even when the API call itself fails', async () => {
    mockedApi.logout.mockRejectedValue(new Error('network down'));
    renderApp();
    await screen.findByTestId('sidebar');

    fireEvent.click(screen.getByText('logout'));

    expect(await screen.findByTestId('login-view')).toBeTruthy();
  });

  describe('Projekt-/Sitzungswechsel', () => {
    async function loginWithActiveSession(session: ChatSession, projects: Project[] = [projectA, projectB]) {
      mockedApi.getProjects.mockResolvedValue(axiosResponse(projects));
      mockedApi.getChatSessions.mockResolvedValue(axiosResponse([session]));
      mockedApi.getChatMessages.mockResolvedValue(axiosResponse([
        { id: 1, role: 'user', content: 'Wie hoch ist der Zins?', metadata_json: {} },
        { id: 2, role: 'assistant', content: 'Antwort', sources_json: [] },
      ]));
      renderApp();
      await screen.findByTestId('sidebar');

      fireEvent.click(screen.getByText(`select-session-${session.id}`));
      await waitFor(() => expect(screen.getByTestId('sidebar-active-session').textContent).toBe(String(session.id)));
      await waitFor(() => expect(screen.getByTestId('panel-messages-0').textContent).toBe('2'));
      routerPush.mockClear();
    }

    it('resets the chat when switching to a project different from the active session\'s own project', async () => {
      await loginWithActiveSession(chatSession());

      fireEvent.click(screen.getByText('select-project-2'));

      await waitFor(() => expect(screen.getByTestId('sidebar-active-session').textContent).toBe('none'));
      expect(screen.getByTestId('panel-messages-0').textContent).toBe('0');
      expect(routerPush).toHaveBeenCalledWith('/workspace');
      expect(await screen.findByText('Projekt "Zinsberechnung" ausgewählt')).toBeTruthy();
    });

    it('does not reset the chat when re-selecting the active session\'s own project', async () => {
      await loginWithActiveSession(chatSession());

      fireEvent.click(screen.getByText('select-project-1'));

      await waitFor(() => expect(screen.getByTestId('sidebar-selected-project').textContent).toBe('Kontoführung'));
      expect(screen.getByTestId('sidebar-active-session').textContent).toBe('7');
      expect(screen.getByTestId('panel-messages-0').textContent).toBe('2');
      expect(routerPush).not.toHaveBeenCalled();
    });

    it('resets the chat and shows the general-context toast when deselecting the project', async () => {
      await loginWithActiveSession(chatSession());

      fireEvent.click(screen.getByText('select-no-project'));

      await waitFor(() => expect(screen.getByTestId('sidebar-active-session').textContent).toBe('none'));
      expect(screen.getByTestId('panel-messages-0').textContent).toBe('0');
      expect(await screen.findByText('Allgemeiner Kontext ausgewählt')).toBeTruthy();
    });

    it('refuses to focus a project that is still being analyzed, without touching the active session', async () => {
      const stillParsing = project({ id: 3, name: 'Neuimport', status: 'parsing', url: 'https://git.example/repo' });
      await loginWithActiveSession(chatSession(), [projectA, projectB, stillParsing]);

      fireEvent.click(screen.getByText('select-project-3'));

      expect(await screen.findByText('Projekt "Neuimport" wird noch analysiert und kann noch nicht fokussiert werden.')).toBeTruthy();
      expect(screen.getByTestId('sidebar-active-session').textContent).toBe('7');
      expect(screen.getByTestId('panel-messages-0').textContent).toBe('2');
      expect(routerPush).not.toHaveBeenCalled();
    });

    it('starts a new chat while keeping the current project focus', async () => {
      await loginWithActiveSession(chatSession());

      fireEvent.click(screen.getByText('start-new-chat'));

      await waitFor(() => expect(screen.getByTestId('sidebar-active-session').textContent).toBe('none'));
      expect(screen.getByTestId('panel-messages-0').textContent).toBe('0');
      expect(screen.getByTestId('sidebar-selected-project').textContent).toBe('Kontoführung');
      expect(routerPush).toHaveBeenCalledWith('/workspace');
    });

    // handleFileSelect trägt seine eigene Reset-Prüfung (unabhängig von
    // handleProjectSelect): eine projektlose Sitzung hält selectedProject nicht
    // nach, sodass ein Dateiaufruf im weiterhin fokussierten Projekt hier zum
    // ersten Mal einen Konflikt zwischen Sitzung und Fokus aufdeckt.
    it('resets the chat session when a file is opened while the active session has no project of its own', async () => {
      mockedApi.getProjects.mockResolvedValue(axiosResponse([projectA]));
      const looseSession = chatSession({ id: 9, uuid: 'chat-9', project_id: null });
      mockedApi.getChatSessions.mockResolvedValue(axiosResponse([looseSession]));
      mockedApi.getChatMessages.mockResolvedValue(axiosResponse([
        { id: 1, role: 'user', content: 'Allgemeine Frage', metadata_json: {} },
      ]));
      mockedApi.getProjectFiles.mockResolvedValue(axiosResponse(['ACCOUNT.cbl']));
      renderApp();
      await screen.findByTestId('sidebar');

      fireEvent.click(screen.getByText('select-project-1'));
      await waitFor(() => expect(screen.getByTestId('sidebar-selected-project').textContent).toBe('Kontoführung'));

      fireEvent.click(screen.getByText('select-session-9'));
      await waitFor(() => expect(screen.getByTestId('sidebar-active-session').textContent).toBe('9'));
      // Die projektlose Sitzung hat keinen eigenen Projekt-Zweig durchlaufen --
      // der Fokus bleibt beim zuvor gewählten Projekt A.
      expect(screen.getByTestId('sidebar-selected-project').textContent).toBe('Kontoführung');

      fireEvent.click(screen.getByText('sidebar-select-file'));

      await waitFor(() => expect(screen.getByTestId('sidebar-active-session').textContent).toBe('none'));
    });

    it('switches to the search result\'s project before focusing its document', async () => {
      await loginWithActiveSession(chatSession(), [projectA, projectB]);

      fireEvent.click(screen.getByText('select-document-result'));

      await waitFor(() => expect(screen.getByTestId('sidebar-selected-project').textContent).toBe('Zinsberechnung'));
      // Der Projektwechsel allein hat schon zurückgesetzt (Sitzung 7 gehört zu
      // Projekt 1) -- der Dokumentaufruf selbst legt keine zweite Sitzung an.
      await waitFor(() => expect(screen.getByTestId('sidebar-active-session').textContent).toBe('none'));
    });

    it('switches to the search result project before opening a Java entity in the editor', async () => {
      mockedApi.getProjects.mockResolvedValue(axiosResponse([projectA, projectB]));
      renderApp();
      await screen.findByTestId('sidebar');

      fireEvent.click(screen.getByText('select-java-entity-result'));

      await waitFor(() => expect(screen.getByTestId('sidebar-selected-project').textContent).toBe('Zinsberechnung'));
      await waitFor(() => expect(mockedApi.getKnowledgeSourceContent).toHaveBeenCalledWith(
        55,
        'src/main/java/com/acme/PaymentService.java',
      ));
    });
  });

  describe('?chat=-URL-Synchronisation', () => {
    it('selects the session matching the ?chat= parameter once sessions have loaded', async () => {
      searchParamsValue = new URLSearchParams('chat=chat-7');
      mockedApi.getProjects.mockResolvedValue(axiosResponse([projectA]));
      mockedApi.getChatSessions.mockResolvedValue(axiosResponse([chatSession()]));
      mockedApi.getChatMessages.mockResolvedValue(axiosResponse([{ id: 1, role: 'assistant', content: 'Antwort', sources_json: [] }]));

      renderApp();

      await waitFor(() => expect(screen.getByTestId('sidebar-active-session').textContent).toBe('7'));
    });

    it('fetches an unrecognized ?chat= session by UUID from the backend and selects it', async () => {
      searchParamsValue = new URLSearchParams('chat=shared-99');
      mockedApi.getProjects.mockResolvedValue(axiosResponse([projectA]));
      mockedApi.getChatSessions.mockResolvedValue(axiosResponse([]));
      const shared = chatSession({ id: 42, uuid: 'shared-99', title: 'Geteilte Sitzung', project_id: null });
      mockedApi.getChatSessionByUuid.mockResolvedValue(axiosResponse(shared));

      renderApp();

      await waitFor(() => expect(mockedApi.getChatSessionByUuid).toHaveBeenCalledWith('shared-99'));
      await waitFor(() => expect(screen.getByTestId('sidebar-active-session').textContent).toBe('42'));
    });
  });
});
