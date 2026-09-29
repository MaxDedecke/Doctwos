import { axiosResponse } from '@/test/http';
/**
 * Regressionstest für O-038: das Speicher-Icon in der Header-Bar erscheint nur,
 * wenn der Chat leer ist UND eine zweite View offen ist -- sonst ist ein reiner
 * Graph-/Code-View-Befund ohne Chat-Nutzung nicht teil-/konservierbar, weil
 * eine Sitzung sonst erst mit der ersten Chat-Nachricht entsteht.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GlobalSearch } from './GlobalSearch';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { api } from '@/app/services/api';

function renderGlobalSearch(overrides: Partial<React.ComponentProps<typeof GlobalSearch>> = {}) {
  return render(
    <LanguageProvider>
      <GlobalSearch
        theme="dark"
        setTheme={vi.fn()}
        projects={[]}
        connectedSources={[]}
        onSelectResult={vi.fn()}
        isSidebarOpen={true}
        setIsSidebarOpen={vi.fn()}
        setIsSettingsOpen={vi.fn()}
        onOpenGraphView={vi.fn()}
        panelConfigs={['chat', 'graph']}
        onAddPanel={vi.fn()}
        selectedProject={null}
        onProjectSelect={vi.fn()}
        onShareChat={vi.fn()}
        canSaveSessionWithoutChat={false}
        hasActiveSessionWithoutChat={false}
        onSaveSessionWithoutChat={vi.fn()}
        onUpdateSessionSnapshot={vi.fn()}
        currentUser={null}
        {...overrides}
      />
    </LanguageProvider>
  );
}

describe('GlobalSearch save-session-without-chat button', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('is hidden when the chat has messages or only one view is open', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    renderGlobalSearch({ canSaveSessionWithoutChat: false });
    // LanguageProvider defaults to German (see LanguageContext.tsx) -- assert
    // on the real de.json string, not the translation key.
    expect(screen.queryByTitle('Sitzung speichern (Chat wurde noch nicht benutzt)')).toBeNull();
  });

  it('appears when the chat is empty and a second view is open, and opens the naming dialog', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    renderGlobalSearch({ canSaveSessionWithoutChat: true });

    const button = screen.getByTitle('Sitzung speichern (Chat wurde noch nicht benutzt)');
    expect(button).toBeTruthy();

    fireEvent.click(button);
    expect(screen.getByPlaceholderText('Name der Sitzung')).toBeTruthy();
  });

  it('calls onSaveSessionWithoutChat with the trimmed title when confirmed', async () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    const onSaveSessionWithoutChat = vi.fn().mockResolvedValue(undefined);
    renderGlobalSearch({ canSaveSessionWithoutChat: true, onSaveSessionWithoutChat });

    fireEvent.click(screen.getByTitle('Sitzung speichern (Chat wurde noch nicht benutzt)'));
    const input = screen.getByPlaceholderText('Name der Sitzung');
    fireEvent.change(input, { target: { value: '  Graph-Befund  ' } });

    await act(async () => {
      fireEvent.click(screen.getByText('Speichern'));
    });

    expect(onSaveSessionWithoutChat).toHaveBeenCalledWith('Graph-Befund');
  });

  // O-038 Folgefix: ist bereits eine chat-lose Sitzung aktiv, darf der Klick
  // nicht erneut den Namens-Dialog öffnen (das würde eine zweite Sitzung
  // anlegen) -- stattdessen wird direkt aktualisiert.
  it('updates the existing session directly instead of reopening the dialog when one is already active', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    const onSaveSessionWithoutChat = vi.fn();
    const onUpdateSessionSnapshot = vi.fn();
    renderGlobalSearch({
      canSaveSessionWithoutChat: true,
      hasActiveSessionWithoutChat: true,
      onSaveSessionWithoutChat,
      onUpdateSessionSnapshot,
    });

    const button = screen.getByTitle('Sitzung mit aktuellem Stand aktualisieren');
    fireEvent.click(button);

    expect(onUpdateSessionSnapshot).toHaveBeenCalledTimes(1);
    expect(onSaveSessionWithoutChat).not.toHaveBeenCalled();
    expect(screen.queryByPlaceholderText('Name der Sitzung')).toBeNull();
  });
});

describe('GlobalSearch collapsible search bar', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const toggle = () => document.getElementById('global-search-toggle') as HTMLButtonElement;
  const input = () => document.getElementById('global-search-input') as HTMLInputElement;
  // Die Leiste bleibt im DOM und animiert ihre Breite; der Zustand steckt in aria-expanded.
  const isExpanded = () => toggle().getAttribute('aria-expanded') === 'true';

  it('starts collapsed into a search icon and keeps the hidden input out of reach', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    renderGlobalSearch();

    expect(isExpanded()).toBe(false);
    expect(toggle().getAttribute('aria-label')).toBe('Suche öffnen');
    expect(input().getAttribute('aria-hidden')).toBe('true');
    expect(input().tabIndex).toBe(-1);
    expect(toggle().parentElement!.className).toContain('w-9');
  });

  it('expands on click, animating the bar width, and focuses the input', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    renderGlobalSearch();

    fireEvent.click(toggle());

    expect(isExpanded()).toBe(true);
    expect(toggle().getAttribute('aria-label')).toBe('Suche schließen');
    expect(toggle().parentElement!.className).toContain('w-[min(28rem,45vw)]');
    expect(toggle().parentElement!.className).toContain('transition-[width');
    expect(input().getAttribute('aria-hidden')).toBe('false');
    expect(document.activeElement).toBe(input());
  });

  it('shrinks back into the icon when the magnifier inside the bar is clicked again and clears the query', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    vi.spyOn(api, 'searchGlobal').mockResolvedValue(axiosResponse({ results: [], total: 0, counts: {} }));
    renderGlobalSearch();
    fireEvent.click(toggle());
    fireEvent.change(input(), { target: { value: 'ZAHLUNG' } });

    fireEvent.click(toggle());

    expect(isExpanded()).toBe(false);
    expect(toggle().parentElement!.className).toContain('w-9');
    expect(input().value).toBe('');
    expect(toggle().getAttribute('aria-label')).toBe('Suche öffnen');
  });

  it('collapses again on Escape while the query is empty', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    renderGlobalSearch();
    fireEvent.click(toggle());

    fireEvent.keyDown(input(), { key: 'Escape' });

    expect(isExpanded()).toBe(false);
  });

  it('stays open on Escape while a query is typed', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    vi.spyOn(api, 'searchGlobal').mockResolvedValue(axiosResponse({ results: [], total: 0, counts: {} }));
    renderGlobalSearch();
    fireEvent.click(toggle());
    fireEvent.change(input(), { target: { value: 'ZAHLUNG' } });

    fireEvent.keyDown(input(), { key: 'Escape' });

    expect(isExpanded()).toBe(true);
  });

  it('collapses an empty search bar on an outside click', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    renderGlobalSearch();
    fireEvent.click(toggle());

    fireEvent.mouseDown(document.body);

    expect(isExpanded()).toBe(false);
  });

  it('opens and focuses the search with Ctrl+K', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    renderGlobalSearch();

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });

    expect(isExpanded()).toBe(true);
    expect(document.activeElement).toBe(input());
  });

  it('shows the scope filter only while the bar is expanded', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    renderGlobalSearch();
    expect(screen.queryByTitle(/filterTitle|Suchbereich/)).toBeNull();

    fireEvent.click(toggle());

    expect(screen.getByTitle(/filterTitle|Suchbereich/)).toBeTruthy();
  });
});

describe('GlobalSearch privileged views', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('hides the Link-Manager from non-admin users even when the feature is enabled', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    renderGlobalSearch({ currentUser: { is_admin: false } });
    fireEvent.click(screen.getByTitle('Ansicht hinzufügen'));
    expect(screen.queryByText('🔗 Link Manager')).toBeNull();
  });

  it('shows the Link-Manager only to admins', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    renderGlobalSearch({ currentUser: { is_admin: true } });
    fireEvent.click(screen.getByTitle('Ansicht hinzufügen'));
    expect(screen.getByText('🔗 Link Manager')).toBeTruthy();
  });
});

describe('GlobalSearch add-view menu', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('offers the same view types as the type selector inside a view, including Agentensuche and Erkenntnisse', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    renderGlobalSearch({ currentUser: { is_admin: true }, panelConfigs: ['code'] });
    fireEvent.click(screen.getByTitle('Ansicht hinzufügen'));

    for (const label of [
      '💬 Chat-Ansicht', '💻 Code-Editor', '📖 Dokumentation', '🕸️ Wissensnetz (Graph)', '🔎 Agentensuche',
      '🔀 Process View', '🌐 Web-Vorschau', '🔗 Link Manager', '💡 Erkenntnisse',
    ]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it('opens a search or insights view via the menu', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    const onAddPanel = vi.fn();
    renderGlobalSearch({ currentUser: { is_admin: false }, panelConfigs: ['chat'], onAddPanel });

    fireEvent.click(screen.getByTitle('Ansicht hinzufügen'));
    fireEvent.click(screen.getByText('🔎 Agentensuche'));
    expect(onAddPanel).toHaveBeenLastCalledWith('search');

    fireEvent.click(screen.getByTitle('Ansicht hinzufügen'));
    fireEvent.click(screen.getByText('💡 Erkenntnisse'));
    expect(onAddPanel).toHaveBeenLastCalledWith('insights');
  });
});

describe('GlobalSearch Java entity navigation', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders a Java entity result and forwards its parser metadata on selection', async () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    const javaResult = {
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
    };
    const searchGlobal = vi.spyOn(api, 'searchGlobal').mockResolvedValue(axiosResponse({
      results: [javaResult],
      total: 1,
      counts: { entity: 1 },
    }));
    const onSelectResult = vi.fn();

    renderGlobalSearch({ onSelectResult });
    fireEvent.click(screen.getByRole('button', { name: 'Suche öffnen' }));
    fireEvent.change(screen.getByPlaceholderText('Programm, Paragraph oder Dokument suchen… (Strg+K)'), {
      target: { value: 'PaymentService' },
    });

    fireEvent.click(await screen.findByRole('button', { name: /PaymentService/ }));

    expect(searchGlobal).toHaveBeenCalledWith('PaymentService', expect.objectContaining({ limit: 6 }));
    expect(onSelectResult).toHaveBeenCalledWith(javaResult);
  });
});
