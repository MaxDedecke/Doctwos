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
    fireEvent.click(screen.getByTitle('Ansicht'));
    expect(screen.queryByText('🔗 Link Manager')).toBeNull();
  });

  it('shows the Link-Manager only to admins', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    renderGlobalSearch({ currentUser: { is_admin: true } });
    fireEvent.click(screen.getByTitle('Ansicht'));
    expect(screen.getByText('🔗 Link Manager')).toBeTruthy();
  });
});

describe('GlobalSearch add-view menu', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('offers the same view types as the type selector inside a view, including Erkenntnisse', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    renderGlobalSearch({ currentUser: { is_admin: true }, panelConfigs: ['code'] });
    fireEvent.click(screen.getByTitle('Ansicht'));

    for (const label of [
      '💬 Chat', '💻 Code-Viewer', '📖 Doku Viewer', '🕸️ Wissensgraph',
      '🔀 Prozess Viewer', '🌐 Web Viewer', '🔗 Link Manager', '💡 Erkenntnisse',
    ]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it('opens an insights view via the menu and offers no agent search view anymore', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    const onAddPanel = vi.fn();
    renderGlobalSearch({ currentUser: { is_admin: false }, panelConfigs: ['chat'], onAddPanel });

    fireEvent.click(screen.getByTitle('Ansicht'));
    expect(screen.queryByText('🔎 Agentensuche')).toBeNull();
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

    expect(searchGlobal).toHaveBeenCalledWith('PaymentService', expect.objectContaining({ limit: 15 }));
    expect(onSelectResult).toHaveBeenCalledWith(javaResult);
  });
});

describe('GlobalSearch manual loading per category', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const hit = (type: string, id: number) => ({
    node_type: type, node_id: id, node_label: `${type}-${id}`, node_url: null, node_meta: {},
  });
  const many = (type: string, from: number, count: number) => Array.from({ length: count }, (_, i) => hit(type, from + i));

  const openAndSearch = async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Suche öffnen' }));
    fireEvent.change(screen.getByPlaceholderText('Programm, Paragraph oder Dokument suchen… (Strg+K)'), { target: { value: 'ZAHLUNG' } });
    await screen.findByText('entity-1');
  };

  it('requests 15 hits per category initially and never loads more by scrolling', async () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    const searchGlobal = vi.spyOn(api, 'searchGlobal').mockResolvedValue(axiosResponse({
      results: [...many('entity', 1, 15), ...many('document', 100, 4)], total: 19, counts: { entity: 40, document: 4 },
    }));
    renderGlobalSearch();
    await openAndSearch();

    const scroller = document.querySelector('.overflow-y-auto') as HTMLElement;
    Object.defineProperty(scroller, 'scrollHeight', { value: 500, configurable: true });
    Object.defineProperty(scroller, 'clientHeight', { value: 400, configurable: true });
    fireEvent.scroll(scroller, { target: { scrollTop: 100 } });
    fireEvent.scroll(scroller, { target: { scrollTop: 100 } });

    expect(searchGlobal).toHaveBeenCalledTimes(1);
    expect(searchGlobal).toHaveBeenCalledWith('ZAHLUNG', expect.objectContaining({ limit: 15 }));
    expect(screen.getByText('document-100')).toBeTruthy();
  });

  it('offers a load-more button only for categories with further hits and shows the remaining count', async () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    vi.spyOn(api, 'searchGlobal').mockResolvedValue(axiosResponse({
      results: [...many('entity', 1, 15), ...many('document', 100, 4)], total: 19, counts: { entity: 40, document: 4 },
    }));
    renderGlobalSearch();
    await openAndSearch();

    expect(screen.getByTestId('global-search-more-entity').textContent).toContain('15');
    expect(screen.getByTestId('global-search-more-entity').textContent).toContain('25');
    expect(screen.queryByTestId('global-search-more-document')).toBeNull();
  });

  it('loads more for exactly one category on click and leaves the others untouched', async () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    const searchGlobal = vi.spyOn(api, 'searchGlobal')
      .mockResolvedValueOnce(axiosResponse({
        results: [...many('entity', 1, 15), ...many('document', 100, 3)], total: 18, counts: { entity: 40, document: 3 },
      }))
      .mockResolvedValueOnce(axiosResponse({ results: many('entity', 1, 30), total: 30, counts: { entity: 40 } }));
    renderGlobalSearch();
    await openAndSearch();

    fireEvent.click(screen.getByTestId('global-search-more-entity'));

    await screen.findByText('entity-30');
    expect(searchGlobal).toHaveBeenLastCalledWith('ZAHLUNG', expect.objectContaining({ types: 'entity', limit: 30 }));
    expect(screen.getByText('document-100')).toBeTruthy();
    expect(screen.getByText('document-102')).toBeTruthy();
    expect(screen.getByTestId('global-search-more-entity').textContent).toContain('10');
  });

  it('drops a load-more answer that arrives after the query changed', async () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue(axiosResponse({ jobs: [], active_count: 0 }));
    let resolveMore: (value: unknown) => void = () => {};
    vi.spyOn(api, 'searchGlobal')
      .mockResolvedValueOnce(axiosResponse({ results: many('entity', 1, 15), total: 15, counts: { entity: 40 } }))
      .mockReturnValueOnce(new Promise((resolve) => { resolveMore = resolve; }) as never)
      .mockResolvedValue(axiosResponse({ results: [hit('entity', 900)], total: 1, counts: { entity: 1 } }));
    renderGlobalSearch();
    await openAndSearch();
    fireEvent.click(screen.getByTestId('global-search-more-entity'));

    fireEvent.change(screen.getByPlaceholderText('Programm, Paragraph oder Dokument suchen… (Strg+K)'), { target: { value: 'NEU' } });
    await screen.findByText('entity-900');
    await act(async () => { resolveMore(axiosResponse({ results: many('entity', 1, 30), total: 30, counts: { entity: 40 } })); });

    expect(screen.queryByText('entity-30')).toBeNull();
    expect(screen.getByText('entity-900')).toBeTruthy();
  });
});
