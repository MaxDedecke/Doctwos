import type { CodeEntity } from '@/types/domain';
/**
 * O-060: `LinkManagerView.tsx` hatte keinen Test -- das manuelle Verknüpfen und
 * Bewerten von Quellen (DOC-F-081) war damit vollständig ungeprüft, obwohl es
 * die einzige Stelle ist, an der ein Mensch die vom Parser/LLM erzeugten
 * Verknüpfungen korrigiert.
 *
 * Die Ansicht spricht ihr Backend direkt über `fetch` an (nicht über den
 * axios-`api`-Wrapper), deshalb wird hier ein nach URL routender fetch-Stub
 * benutzt statt eines Modul-Mocks. `TopicsPanel` ist als eigener,
 * Admin-exklusiver Bereich mit eigenem Datenabruf gestubbt -- geprüft wird nur,
 * ob der Link Manager ihn überhaupt anbietet, nicht sein Innenleben.
 *
 * Die drei Doku-Bereiche des Punktes (Filterleiste, manueller Picker,
 * Linkkarten-Interaktionen) sind unten je ein `describe`-Block.
 *
 * O-165: Die Linkliste rendert gefenstert (@tanstack/react-virtual) und misst
 * dafür `offsetHeight`, das jsdom mangels Layout immer als 0 meldet -- ohne den
 * Spy in `beforeEach` hielte der Virtualizer den Container für 0px hoch und
 * würde keine einzige Karte rendern (gleiches Vorgehen wie in `Sidebar.test.tsx`).
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { LinkManagerView } from './LinkManagerView';

vi.mock('./TopicsPanel', () => ({ TopicsPanel: () => <div data-testid="topics-panel" /> }));

const PROJECT = { id: 3, name: 'Rentenkasse' };

type EntityLink = {
  id: number; entity_id: number; entity?: CodeEntity; doc_title: string; doc_url: string | null;
  source_type: string | null; score: number | null; link_type: string; status: string;
  context: string | null; created_by: string;
};

function entityLink(overrides: Partial<EntityLink> = {}): EntityLink {
  return {
    id: 1,
    entity_id: 11,
    entity: { id: 11, name: 'ZAHLUNG', type: 'program', file_path: 'src/ZAHLUNG.cbl', start_line: 12, end_line: 40 },
    doc_title: 'Zahlungslauf-Handbuch',
    doc_url: 'https://wiki/zahlung',
    source_type: 'Confluence',
    score: 0.8,
    link_type: 'semantic',
    status: 'pending',
    context: null,
    created_by: 'system',
    ...overrides,
  };
}

function knowledgeLink(overrides: Record<string, unknown> = {}) {
  return {
    id: 50,
    source_a: { type: 'document', title: 'Fachkonzept', url: null, source_type: 'Confluence' },
    source_b: { type: 'document', title: 'Betriebshandbuch', url: null, source_type: 'Confluence' },
    score: 0.6,
    link_type: 'semantic',
    status: 'pending',
    context: null,
    created_by: 'system',
    ...overrides,
  };
}

interface Routes {
  entityLinks?: EntityLink[];
  entityCounts?: { pending: number; approved: number; rejected: number };
  knowledgeLinks?: ReturnType<typeof knowledgeLink>[];
  knowledgeCounts?: { pending: number; approved: number; rejected: number };
  entities?: Array<Omit<CodeEntity, 'id' | 'start_line'> & { id: number | string; start_line?: number }>;
  docSearch?: Array<{ title: string; url?: string | null; source_type?: string | null }>;
  patchOk?: boolean;
  postOk?: boolean;
  postError?: string;
  llmReview?: { score?: number; context?: string; detail?: string };
  llmReviewOk?: boolean;
}

/** fetch-Stub, der die Endpunkte der Ansicht nach URL + Methode beantwortet. */
function stubFetch(routes: Routes = {}) {
  const json = (body: unknown, ok = true, status = 200) => ({ ok, status, json: async () => body });
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = (init?.method || 'GET').toUpperCase();

    if (method === 'PATCH') return json({ context: JSON.parse(String(init!.body)).context ?? null }, routes.patchOk !== false);
    if (method === 'DELETE') return json({}, true);
    if (url.includes('/llm-review')) return json(routes.llmReview ?? { score: 0.95, context: 'LLM-Begründung' }, routes.llmReviewOk !== false);
    if (method === 'POST' && url.includes('/compute')) return json({ started: true });
    if (method === 'POST') return json(routes.postOk === false ? { detail: routes.postError ?? 'Serverfehler' } : {}, routes.postOk !== false);

    if (url.includes('/doc-chunks/search')) return json(routes.docSearch ?? []);
    if (url.includes('/entities')) return json(routes.entities ?? []);
    if (url.includes('/link-recommendations')) {
      return json({
        links: routes.entityLinks ?? [],
        counts: routes.entityCounts ?? { pending: (routes.entityLinks ?? []).length, approved: 0, rejected: 0 },
      });
    }
    if (url.includes('/knowledge-links/counts')) {
      return json(routes.knowledgeCounts ?? {
        pending: (routes.knowledgeLinks ?? []).length, approved: 0, rejected: 0,
      });
    }
    if (url.includes('/knowledge-links')) return json(routes.knowledgeLinks ?? []);
    return json({});
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function renderView(props: Partial<React.ComponentProps<typeof LinkManagerView>> = {}) {
  const showToast = vi.fn();
  const view = render(
    <LanguageProvider>
      <LinkManagerView selectedProject={PROJECT} theme="dark" showToast={showToast} {...(props)} />
    </LanguageProvider>
  );
  return { ...view, showToast };
}

/** Die URLs aller Aufrufe, die zu Methode und Fragment passen. */
function calls(fetchMock: ReturnType<typeof stubFetch>, fragment: string, method = 'GET'): string[] {
  return fetchMock.mock.calls
    .filter(([url, init]) => String(url).includes(fragment) && ((init?.method || 'GET').toUpperCase() === method))
    .map(([url]) => String(url));
}

function bodyOf(fetchMock: ReturnType<typeof stubFetch>, fragment: string, method: string): Record<string, unknown> {
  const call = [...fetchMock.mock.calls].reverse()
    .find(([url, init]) => String(url).includes(fragment) && (init?.method || '').toUpperCase() === method);
  return JSON.parse(String((call![1] as RequestInit).body));
}

describe('LinkManagerView', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(600);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  describe('Filterleiste', () => {
    it('zählt Code- und Wissens-Links in den Tabs zusammen', async () => {
      stubFetch({
        entityLinks: [entityLink()],
        entityCounts: { pending: 1, approved: 4, rejected: 2 },
        knowledgeLinks: [knowledgeLink()],
        knowledgeCounts: { pending: 1, approved: 1, rejected: 1 },
      });

      renderView();

      // Beide Zählerquellen (Entity-Liste und /knowledge-links/counts) werden
      // je Tab aufaddiert.
      const pendingTab = await screen.findByRole('button', { name: /^Offen/ });
      await waitFor(() => expect(within(pendingTab).getByText('2')).toBeTruthy());
      expect(within(screen.getByRole('button', { name: /^Bestätigt/ })).getByText('5')).toBeTruthy();
      expect(within(screen.getByRole('button', { name: /^Abgelehnt/ })).getByText('3')).toBeTruthy();
    });

    it('lädt beim Tabwechsel mit dem neuen Status nach', async () => {
      const fetchMock = stubFetch({ entityLinks: [entityLink()] });

      renderView();
      await screen.findByText('ZAHLUNG');

      fireEvent.click(screen.getByRole('button', { name: /^Bestätigt/ }));

      await waitFor(() => expect(calls(fetchMock, '/link-recommendations').some(u => u.includes('status=approved'))).toBe(true));
      expect(calls(fetchMock, '/knowledge-links').some(u => u.includes('status=approved'))).toBe(true);
    });

    it('bietet den Score-Filter nur im Offen-Tab an und schickt ihn als min_score mit', async () => {
      const fetchMock = stubFetch({ entityLinks: [entityLink()] });

      renderView();
      await screen.findByText('ZAHLUNG');

      fireEvent.change(screen.getByDisplayValue('Alle %'), { target: { value: '80' } });
      await waitFor(() => expect(calls(fetchMock, '/link-recommendations').some(u => u.includes('min_score=0.8'))).toBe(true));

      fireEvent.click(screen.getByRole('button', { name: /^Abgelehnt/ }));
      await waitFor(() => expect(screen.queryByDisplayValue('Alle %')).toBeNull());
    });

    it('sucht über beide Seiten und die Bildunterschrift einer Karte', async () => {
      stubFetch({
        entityLinks: [entityLink()],
        knowledgeLinks: [knowledgeLink()],
      });

      renderView();
      await screen.findByText('ZAHLUNG');
      const searchBox = screen.getByPlaceholderText('Suchen…');

      // linke Seite
      fireEvent.change(searchBox, { target: { value: 'zahlung' } });
      await waitFor(() => expect(screen.queryByText('Fachkonzept')).toBeNull());
      expect(screen.getByText('ZAHLUNG')).toBeTruthy();

      // rechte Seite
      fireEvent.change(searchBox, { target: { value: 'betriebshandbuch' } });
      await waitFor(() => expect(screen.queryByText('ZAHLUNG')).toBeNull());
      expect(screen.getByText('Fachkonzept')).toBeTruthy();

      // Bildunterschrift (Dateipfad der Entity)
      fireEvent.change(searchBox, { target: { value: 'ZAHLUNG.cbl' } });
      await waitFor(() => expect(screen.getByText('ZAHLUNG')).toBeTruthy());
      expect(screen.queryByText('Fachkonzept')).toBeNull();
    });

    it('filtert nach Verknüpfungsart', async () => {
      stubFetch({ entityLinks: [entityLink()], knowledgeLinks: [knowledgeLink()] });

      renderView();
      await screen.findByText('ZAHLUNG');

      fireEvent.click(screen.getByRole('button', { name: 'Doc ↔ Doc' }));
      await waitFor(() => expect(screen.queryByText('ZAHLUNG')).toBeNull());
      expect(screen.getByText('Fachkonzept')).toBeTruthy();

      fireEvent.click(screen.getByRole('button', { name: 'Code ↔ Doc' }));
      await waitFor(() => expect(screen.queryByText('Fachkonzept')).toBeNull());
      expect(screen.getByText('ZAHLUNG')).toBeTruthy();

      fireEvent.click(screen.getByRole('button', { name: 'Alle' }));
      await waitFor(() => expect(screen.getByText('Fachkonzept')).toBeTruthy());
      expect(screen.getByText('ZAHLUNG')).toBeTruthy();
    });

    it('sortiert die Karten absteigend nach Wahrscheinlichkeit', async () => {
      stubFetch({
        entityLinks: [entityLink({ id: 1, score: 0.4 }), entityLink({ id: 2, score: 0.9, entity: { id: 12, name: 'BUCHUNG', type: 'program', file_path: 'src/BUCHUNG.cbl', start_line: 1 } })],
      });

      renderView();
      await screen.findByText('BUCHUNG');

      const labels = screen.getAllByText(/^(BUCHUNG|ZAHLUNG)$/).map(node => node.textContent);
      expect(labels).toEqual(['BUCHUNG', 'ZAHLUNG']);
    });

    it('merkt sich die Mindest-Wahrscheinlichkeit im Browser und klemmt sie auf 0..100', async () => {
      stubFetch();

      const { unmount } = renderView();
      const input = await screen.findByLabelText('Mindest-Wahrscheinlichkeit');
      expect((input as HTMLInputElement).value).toBe('35');

      fireEvent.change(input, { target: { value: '250' } });
      expect((input as HTMLInputElement).value).toBe('100');
      expect(localStorage.getItem('doctus-link-min-confidence')).toBe('100');

      fireEvent.change(input, { target: { value: '60' } });
      unmount();

      renderView();
      expect(((await screen.findByLabelText('Mindest-Wahrscheinlichkeit')) as HTMLInputElement).value).toBe('60');
    });

    it('startet die automatische Suche mit der eingestellten Mindest-Wahrscheinlichkeit', async () => {
      const fetchMock = stubFetch();

      renderView();
      fireEvent.change(await screen.findByLabelText('Mindest-Wahrscheinlichkeit'), { target: { value: '70' } });

      fireEvent.click(screen.getByRole('button', { name: /Automatisch verknüpfen/ }));

      await waitFor(() => expect(calls(fetchMock, '/compute', 'POST').some(u => u.includes('min_confidence=70'))).toBe(true));
      expect(screen.getByText(/Suche gestartet/)).toBeTruthy();
    });

    it('zeigt den Topics-Bereich nur Admins', async () => {
      stubFetch();

      const { unmount } = renderView({ currentUser: { is_admin: false } });
      await screen.findByRole('button', { name: /^Offen/ });
      expect(screen.queryByRole('button', { name: 'Topics' })).toBeNull();
      unmount();

      renderView({ currentUser: { is_admin: true } });
      fireEvent.click(await screen.findByRole('button', { name: 'Topics' }));
      expect(screen.getByTestId('topics-panel')).toBeTruthy();
    });

    it('meldet eine leere Liste je Tab passend', async () => {
      stubFetch();

      renderView();

      expect(await screen.findByText('Keine offenen Verknüpfungen')).toBeTruthy();
      // Der Hinweis auf die automatische Suche gehört nur zum Offen-Tab.
      expect(screen.getByText(/^Klicke/)).toBeTruthy();

      fireEvent.click(screen.getByRole('button', { name: /^Abgelehnt/ }));

      expect(await screen.findByText('Keine abgelehnten Verknüpfungen')).toBeTruthy();
    });
  });

  describe('große Listen', () => {
    it('rendert nur den sichtbaren Ausschnitt statt aller Karten', async () => {
      const many = Array.from({ length: 400 }, (_, i) => knowledgeLink({
        id: 1000 + i,
        source_a: { type: 'document', title: `Quelle ${i}`, url: null, source_type: 'Confluence' },
        source_b: { type: 'document', title: `Ziel ${i}`, url: null, source_type: 'Confluence' },
      }));
      stubFetch({ knowledgeLinks: many, knowledgeCounts: { pending: many.length, approved: 0, rejected: 0 } });

      renderView();

      // Die erste Karte ist da, der Zähler kennt alle 400 -- im DOM hängt aber
      // nur das gefensterte Stück (600px hoher Container, siehe offsetHeight-Spy).
      await screen.findByText('Quelle 0');
      const pendingTab = screen.getByRole('button', { name: /^Offen/ });
      expect(within(pendingTab).getByText('400')).toBeTruthy();
      const rendered = screen.getAllByText(/^Quelle \d+$/).length;
      expect(rendered).toBeGreaterThan(0);
      expect(rendered).toBeLessThan(50);
      expect(screen.queryByText('Quelle 399')).toBeNull();
    });

    it('holt die Tab-Zähler über /knowledge-links/counts statt über die vollen Statuslisten', async () => {
      const fetchMock = stubFetch({ knowledgeLinks: [knowledgeLink()] });

      renderView();
      await screen.findByText('Fachkonzept');

      expect(calls(fetchMock, '/knowledge-links/counts')).toHaveLength(1);
      // Genau eine Listenabfrage: die für den offenen Tab.
      const listCalls = calls(fetchMock, '/knowledge-links').filter(u => !u.includes('/counts'));
      expect(listCalls).toHaveLength(1);
      expect(listCalls[0]).toContain('status=pending');
    });
  });

  describe('Alle-100%-Bestätigen', () => {
    const perfect = entityLink({ id: 1, score: 1 });
    const almost = entityLink({ id: 2, score: 0.9, entity: { id: 12, name: 'BUCHUNG', type: 'program', file_path: 'src/BUCHUNG.cbl', start_line: 1 } });

    it('bleibt verborgen, solange kein Treffer bei 100 % liegt', async () => {
      stubFetch({ entityLinks: [almost] });

      renderView();
      await screen.findByText('BUCHUNG');

      expect(screen.queryByRole('button', { name: /Alle 100 % bestätigen/ })).toBeNull();
    });

    it('zählt nur die perfekten Treffer, nicht alle Karten', async () => {
      stubFetch({ entityLinks: [perfect, almost] });

      renderView();
      await screen.findByText('BUCHUNG');

      const button = await screen.findByRole('button', { name: /Alle 100 % bestätigen/ });
      expect(within(button).getByText('1')).toBeTruthy();
    });

    it('verschwindet außerhalb des Offen-Tabs', async () => {
      stubFetch({ entityLinks: [perfect] });

      renderView();
      await screen.findByRole('button', { name: /Alle 100 % bestätigen/ });

      fireEvent.click(screen.getByRole('button', { name: /^Bestätigt/ }));

      await waitFor(() => expect(screen.queryByRole('button', { name: /Alle 100 % bestätigen/ })).toBeNull());
    });

    it('bestätigt alle perfekten Treffer auf einmal und entfernt sie aus der Liste', async () => {
      const fetchMock = stubFetch({ entityLinks: [perfect, almost] });

      const { showToast } = renderView();
      fireEvent.click(await screen.findByRole('button', { name: /Alle 100 % bestätigen/ }));

      await waitFor(() => expect(screen.queryByText('ZAHLUNG')).toBeNull());
      expect(screen.getByText('BUCHUNG')).toBeTruthy();
      expect(calls(fetchMock, '/entity-doc-links/1', 'PATCH')).toHaveLength(1);
      expect(showToast).toHaveBeenCalledWith(expect.stringContaining('1'), 'success');
    });

    it('meldet, wenn ein Teil der Sammelbestätigung scheitert', async () => {
      stubFetch({ entityLinks: [perfect], patchOk: false });

      const { showToast } = renderView();
      fireEvent.click(await screen.findByRole('button', { name: /Alle 100 % bestätigen/ }));

      await waitFor(() => expect(showToast).toHaveBeenCalledWith(expect.stringContaining('nicht bestätigt'), 'error'));
      // Die Karte bleibt stehen, weil der Server sie nicht übernommen hat.
      expect(screen.getByText('ZAHLUNG')).toBeTruthy();
    });
  });

  describe('manueller Picker', () => {
    const entities = [
      { id: 'ent_11', name: 'ZAHLUNG', type: 'program', file_path: 'src/ZAHLUNG.cbl' },
      { id: 'ent_12', name: 'BUCHUNG', type: 'program', file_path: 'src/BUCHUNG.cbl' },
      { id: 'ref_99', name: 'NUR-REFERENZ', type: 'reference', file_path: 'src/EXTERN.cbl' },
    ];
    const docs = [{ title: 'Zahlungslauf-Handbuch', url: 'https://wiki/zahlung', source_type: 'Confluence' }];

    it('ist ohne Projekt gesperrt', async () => {
      stubFetch();

      renderView({ selectedProject: null });

      const button = (await screen.findByText('Manuell')).closest('button') as HTMLButtonElement;
      expect(button.disabled).toBe(true);
      expect(button.title).toBe('Kein Projekt ausgewählt');
    });

    it('fragt zuerst nach der Art der Verknüpfung', async () => {
      stubFetch();

      renderView();
      fireEvent.click(await screen.findByText('Manuell'));

      expect(screen.getByText('Was möchtest du verknüpfen?')).toBeTruthy();
      expect(screen.getByRole('button', { name: /Code-Element ↔ Dokument/ })).toBeTruthy();
      expect(screen.getByRole('button', { name: /Dokument ↔ Dokument/ })).toBeTruthy();
    });

    it('blendet Referenz-Entities aus und sucht über Name und Pfad', async () => {
      stubFetch({ entities });

      renderView();
      fireEvent.click(await screen.findByText('Manuell'));
      fireEvent.click(screen.getByRole('button', { name: /Code-Element ↔ Dokument/ }));

      const entityBox = await screen.findByPlaceholderText('Entity suchen…');
      fireEvent.change(entityBox, { target: { value: 'ung' } });

      await waitFor(() => expect(screen.getAllByText(/^(ZAHLUNG|BUCHUNG)$/).length).toBeGreaterThan(0));
      expect(screen.queryByText('NUR-REFERENZ')).toBeNull();

      fireEvent.change(entityBox, { target: { value: 'BUCHUNG.cbl' } });
      await waitFor(() => expect(screen.getByText('BUCHUNG')).toBeTruthy());
    });

    it('legt eine Code-Dokument-Verknüpfung an und wechselt danach in den Bestätigt-Tab', async () => {
      const fetchMock = stubFetch({ entities, docSearch: docs });

      renderView();
      fireEvent.click(await screen.findByText('Manuell'));
      fireEvent.click(screen.getByRole('button', { name: /Code-Element ↔ Dokument/ }));

      fireEvent.change(await screen.findByPlaceholderText('Entity suchen…'), { target: { value: 'ZAHLUNG' } });
      fireEvent.click(await screen.findByText('ZAHLUNG'));

      const save = (screen.getByText('Verknüpfung speichern').closest('button')) as HTMLButtonElement;
      expect(save.disabled).toBe(true);

      fireEvent.change(screen.getByPlaceholderText('Seitentitel suchen…'), { target: { value: 'Zahlung' } });
      fireEvent.click(await screen.findByText('Zahlungslauf-Handbuch'));
      fireEvent.change(screen.getByPlaceholderText('Wie hängen die beiden inhaltlich zusammen?'), { target: { value: 'Beschreibt den Lauf' } });

      expect(save.disabled).toBe(false);
      fireEvent.click(save);

      await waitFor(() => expect(calls(fetchMock, '/link-recommendations', 'POST')).toHaveLength(1));
      const body = bodyOf(fetchMock, '/link-recommendations', 'POST');
      // "ent_11" wird auf die numerische DB-ID zurückgeführt.
      expect(body.entity_id).toBe(11);
      expect(body.doc_title).toBe('Zahlungslauf-Handbuch');
      expect(body.context).toBe('Beschreibt den Lauf');

      await waitFor(() => expect(screen.queryByText('Verknüpfung speichern')).toBeNull());
      await waitFor(() => expect(calls(fetchMock, '/link-recommendations').some(u => u.includes('status=approved'))).toBe(true));
    });

    it('legt eine Dokument-Dokument-Verknüpfung sofort als bestätigt an', async () => {
      const fetchMock = stubFetch({
        docSearch: [{ title: 'Fachkonzept', url: null, source_type: 'Confluence' }],
      });

      renderView();
      fireEvent.click(await screen.findByText('Manuell'));
      fireEvent.click(screen.getByRole('button', { name: /Dokument ↔ Dokument/ }));

      // Beide Picker sehen identisch aus (gleicher Platzhalter, gleicher Treffer),
      // deshalb wird je Picker über seine Beschriftung eingegrenzt.
      const pickerA = screen.getByText('1 · Erstes Dokument').parentElement!;
      const pickerB = screen.getByText('2 · Zweites Dokument').parentElement!;

      fireEvent.change(within(pickerA).getByPlaceholderText('Seitentitel suchen…'), { target: { value: 'Fach' } });
      fireEvent.click(await within(pickerA).findByRole('button', { name: /Fachkonzept/ }));
      fireEvent.change(within(pickerB).getByPlaceholderText('Seitentitel suchen…'), { target: { value: 'Fach' } });
      fireEvent.click(await within(pickerB).findByRole('button', { name: /Fachkonzept/ }));

      fireEvent.click(screen.getByText('Verknüpfung speichern'));

      await waitFor(() => expect(calls(fetchMock, '/knowledge-links', 'POST')).toHaveLength(1));
      const body = bodyOf(fetchMock, '/knowledge-links', 'POST');
      expect(body.link_type).toBe('manual');
      expect(body.status).toBe('approved');
      expect(body.source_a_title).toBe('Fachkonzept');
      expect(body.source_b_title).toBe('Fachkonzept');
    });

    it('zeigt die Fehlermeldung des Servers und lässt das Formular offen', async () => {
      stubFetch({ entities, docSearch: docs, postOk: false, postError: 'Verknüpfung existiert bereits' });

      renderView();
      fireEvent.click(await screen.findByText('Manuell'));
      fireEvent.click(screen.getByRole('button', { name: /Code-Element ↔ Dokument/ }));
      fireEvent.change(await screen.findByPlaceholderText('Entity suchen…'), { target: { value: 'ZAHLUNG' } });
      fireEvent.click(await screen.findByText('ZAHLUNG'));
      fireEvent.change(screen.getByPlaceholderText('Seitentitel suchen…'), { target: { value: 'Zahlung' } });
      fireEvent.click(await screen.findByText('Zahlungslauf-Handbuch'));

      fireEvent.click(screen.getByText('Verknüpfung speichern'));

      expect(await screen.findByText('Verknüpfung existiert bereits')).toBeTruthy();
      expect(screen.getByText('Verknüpfung speichern')).toBeTruthy();
    });

    it('geht über den Zurück-Pfeil eine Stufe zurück, ohne die Auswahl zu verlieren', async () => {
      stubFetch({ entities });

      renderView();
      fireEvent.click(await screen.findByText('Manuell'));
      fireEvent.click(screen.getByRole('button', { name: /Code-Element ↔ Dokument/ }));
      fireEvent.change(await screen.findByPlaceholderText('Entity suchen…'), { target: { value: 'ZAHLUNG' } });
      fireEvent.click(await screen.findByText('ZAHLUNG'));

      fireEvent.click(screen.getByText('Manuelle Verknüpfung').querySelector('button')!);
      expect(screen.getByText('Was möchtest du verknüpfen?')).toBeTruthy();

      fireEvent.click(screen.getByRole('button', { name: /Code-Element ↔ Dokument/ }));
      expect(screen.getByText('src/ZAHLUNG.cbl')).toBeTruthy();
    });

    it('räumt das Formular erst beim Schließen über das Kreuz auf, nicht beim bloßen Zuklappen', async () => {
      stubFetch({ entities });

      renderView();
      fireEvent.click(await screen.findByText('Manuell'));
      fireEvent.click(screen.getByRole('button', { name: /Code-Element ↔ Dokument/ }));
      fireEvent.change(await screen.findByPlaceholderText('Entity suchen…'), { target: { value: 'ZAHLUNG' } });
      fireEvent.click(await screen.findByText('ZAHLUNG'));

      // Der "Manuell"-Knopf klappt nur auf und zu -- die Auswahl überlebt das.
      fireEvent.click(screen.getByText('Manuell'));
      fireEvent.click(screen.getByText('Manuell'));
      expect(screen.getByText('src/ZAHLUNG.cbl')).toBeTruthy();

      // Das Kreuz dagegen setzt alles zurück, inklusive der Artauswahl.
      const header = screen.getByText('Manuelle Verknüpfung').closest('div')!;
      fireEvent.click(header.querySelector(':scope > button')!);
      fireEvent.click(screen.getByText('Manuell'));
      expect(screen.getByText('Was möchtest du verknüpfen?')).toBeTruthy();
      expect(screen.queryByText('src/ZAHLUNG.cbl')).toBeNull();
    });
  });

  describe('Linkkarten-Interaktionen', () => {
    it('zeigt beide Seiten, die Wahrscheinlichkeit und den passenden Pfeil je Art', async () => {
      stubFetch({ entityLinks: [entityLink()], knowledgeLinks: [knowledgeLink()] });

      renderView();

      expect(await screen.findByText('ZAHLUNG')).toBeTruthy();
      expect(screen.getByText('Zahlungslauf-Handbuch')).toBeTruthy();
      expect(screen.getByText('80%')).toBeTruthy();
      // Code→Doc ist gerichtet, Doc↔Doc nicht.
      expect(screen.getByText('→')).toBeTruthy();
      expect(screen.getByText('↔')).toBeTruthy();
    });

    it('bestätigt eine Verknüpfung, entfernt die Karte und meldet es', async () => {
      const fetchMock = stubFetch({ entityLinks: [entityLink()] });

      const { showToast } = renderView();
      await screen.findByText('ZAHLUNG');

      fireEvent.click(screen.getByTitle('Bestätigen'));

      await waitFor(() => expect(screen.queryByText('ZAHLUNG')).toBeNull());
      expect(bodyOf(fetchMock, '/entity-doc-links/1', 'PATCH').status).toBe('approved');
      expect(showToast).toHaveBeenCalledWith(expect.stringContaining('Zahlungslauf-Handbuch'), 'success');
    });

    it('lässt die Karte stehen, wenn der Server die Änderung ablehnt', async () => {
      stubFetch({ entityLinks: [entityLink()], patchOk: false });

      const { showToast } = renderView();
      await screen.findByText('ZAHLUNG');

      fireEvent.click(screen.getByTitle('Bestätigen'));

      await waitFor(() => expect(showToast).toHaveBeenCalledWith('Verknüpfung konnte nicht aktualisiert werden.', 'error'));
      expect(screen.getByText('ZAHLUNG')).toBeTruthy();
    });

    it('lehnt eine Verknüpfung ab', async () => {
      const fetchMock = stubFetch({ entityLinks: [entityLink()] });

      renderView();
      await screen.findByText('ZAHLUNG');

      fireEvent.click(screen.getByTitle('Ablehnen'));

      await waitFor(() => expect(bodyOf(fetchMock, '/entity-doc-links/1', 'PATCH').status).toBe('rejected'));
    });

    it('bietet je Tab die passenden Aktionen an', async () => {
      stubFetch({ entityLinks: [entityLink()] });

      renderView();
      await screen.findByText('ZAHLUNG');
      expect(screen.getByTitle('Mit LLM prüfen')).toBeTruthy();
      expect(screen.queryByTitle('Entfernen')).toBeNull();

      fireEvent.click(screen.getByRole('button', { name: /^Bestätigt/ }));
      await waitFor(() => expect(screen.getByTitle('Entfernen')).toBeTruthy());
      expect(screen.queryByTitle('Bestätigen')).toBeNull();

      fireEvent.click(screen.getByRole('button', { name: /^Abgelehnt/ }));
      await waitFor(() => expect(screen.getByTitle('Doch bestätigen')).toBeTruthy());
      expect(screen.getByTitle('Löschen')).toBeTruthy();
    });

    it('löscht eine bestätigte Verknüpfung', async () => {
      const fetchMock = stubFetch({ entityLinks: [entityLink({ status: 'approved' })] });

      renderView();
      await screen.findByText('ZAHLUNG');
      fireEvent.click(screen.getByRole('button', { name: /^Bestätigt/ }));

      fireEvent.click(await screen.findByTitle('Entfernen'));

      await waitFor(() => expect(calls(fetchMock, '/entity-doc-links/1', 'DELETE')).toHaveLength(1));
      expect(screen.queryByText('ZAHLUNG')).toBeNull();
    });

    it('lässt eine Verknüpfung vom LLM nachbewerten und übernimmt das Ergebnis', async () => {
      stubFetch({ entityLinks: [entityLink()], llmReview: { score: 0.95, context: 'Beschreibt denselben Lauf' } });

      const { showToast } = renderView();
      await screen.findByText('ZAHLUNG');
      expect(screen.getByText('80%')).toBeTruthy();

      fireEvent.click(screen.getByTitle('Mit LLM prüfen'));

      await waitFor(() => expect(screen.getByText('95%')).toBeTruthy());
      expect(screen.getByText('Beschreibt denselben Lauf')).toBeTruthy();
      expect(showToast).toHaveBeenCalledWith(expect.stringContaining('95'), 'success');
    });

    it('meldet eine gescheiterte LLM-Prüfung, ohne die Karte zu verändern', async () => {
      stubFetch({ entityLinks: [entityLink()], llmReviewOk: false, llmReview: { detail: 'Ollama deaktiviert' } });

      const { showToast } = renderView();
      await screen.findByText('ZAHLUNG');

      fireEvent.click(screen.getByTitle('Mit LLM prüfen'));

      await waitFor(() => expect(showToast).toHaveBeenCalledWith('Ollama deaktiviert', 'error'));
      expect(screen.getByText('80%')).toBeTruthy();
    });

    it('speichert eine nachträglich getippte Beschreibung mit Enter', async () => {
      const fetchMock = stubFetch({ entityLinks: [entityLink()] });

      renderView();
      await screen.findByText('ZAHLUNG');

      fireEvent.click(screen.getByText('+ Beschreibung'));
      const input = screen.getByPlaceholderText('Wie hängt das zusammen?');
      fireEvent.change(input, { target: { value: '  Gehört zum selben Lauf  ' } });
      fireEvent.keyDown(input, { key: 'Enter' });

      await waitFor(() => expect(bodyOf(fetchMock, '/entity-doc-links/1', 'PATCH').context).toBe('Gehört zum selben Lauf'));
      await waitFor(() => expect(screen.getByText('Gehört zum selben Lauf')).toBeTruthy());
    });

    it('verwirft die Bearbeitung mit Escape, ohne etwas zu senden', async () => {
      const fetchMock = stubFetch({ entityLinks: [entityLink({ context: 'Alter Text' })] });

      renderView();
      await screen.findByText('Alter Text');

      fireEvent.click(screen.getByText('Alter Text'));
      const input = screen.getByPlaceholderText('Wie hängt das zusammen?');
      fireEvent.change(input, { target: { value: 'Neuer Text' } });
      fireEvent.keyDown(input, { key: 'Escape' });

      await waitFor(() => expect(screen.getByText('Alter Text')).toBeTruthy());
      expect(calls(fetchMock, '/entity-doc-links/1', 'PATCH')).toHaveLength(0);
    });

    it('schickt keinen Request, wenn die Beschreibung unverändert bleibt', async () => {
      const fetchMock = stubFetch({ entityLinks: [entityLink({ context: 'Alter Text' })] });

      renderView();
      await screen.findByText('Alter Text');

      fireEvent.click(screen.getByText('Alter Text'));
      fireEvent.keyDown(screen.getByPlaceholderText('Wie hängt das zusammen?'), { key: 'Enter' });

      await waitFor(() => expect(screen.getByText('Alter Text')).toBeTruthy());
      expect(calls(fetchMock, '/entity-doc-links/1', 'PATCH')).toHaveLength(0);
    });
  });
});
