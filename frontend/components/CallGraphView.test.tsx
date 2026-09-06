/**
 * O-058: `CallGraphView.tsx` hatte keinen Test -- Fokus-Laden über
 * `/callgraph/focus`, die Hops-Auswahl, die drei Export-Knöpfe
 * (JSON/CSV/GraphML) und das Kapp-Banner waren komplett ungeprüft.
 *
 * Gemockt wird nach demselben Muster wie in `KnowledgeGraphView.test.tsx`:
 * `react-force-graph-2d` braucht Canvas-Maschinerie, die jsdom nicht hat, und
 * wird durch einen Stub ersetzt, der je Knoten einen klickbaren Button rendert
 * (treibt `onNodeClick` ohne echtes Canvas an) und über `ref` die von der
 * Komponente benutzten Kamera-Methoden anbietet. Die Größe des Zeichenfeldes
 * kommt aus einem `ResizeObserver`-Stub -- ohne ihn bleibt `dimensions.width`
 * bei 0 und der Graph wird gar nicht erst gerendert.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { CallGraphView } from './CallGraphView';

const ForceGraph2DStub = React.forwardRef((props: any, ref: any) => {
  React.useImperativeHandle(ref, () => ({
    zoom: () => 1,
    zoomToFit: () => {},
  }));
  return (
    <div data-testid="force-graph-stub">
      {props.graphData.nodes.map((node: any) => (
        <button key={node.id} data-testid={`node-${node.id}`} onClick={() => props.onNodeClick(node)}>
          {node.name}
        </button>
      ))}
      {props.graphData.links.map((link: any) => (
        <span key={link.id} data-testid={`link-${link.id}`} />
      ))}
    </div>
  );
});
ForceGraph2DStub.displayName = 'ForceGraph2DStub';

vi.mock('react-force-graph-2d', () => ({ default: ForceGraph2DStub }));

// Wie in KnowledgeGraphView.test.tsx: ein echter ResizeObserver ruft nie
// synchron aus observe() heraus zurück -- der Stub muss das nachbilden.
class ResizeObserverStub {
  private cb: ResizeObserverCallback;
  constructor(cb: ResizeObserverCallback) { this.cb = cb; }
  observe() {
    queueMicrotask(() => this.cb([{ contentRect: { width: 800, height: 600 } }] as any, this as unknown as ResizeObserver));
  }
  unobserve() {}
  disconnect() {}
}

/** Zwei verbundene Entities -- das Minimum, ab dem der Graph gerendert wird. */
const FOCUS_RESPONSE = {
  nodes: [
    { id: 1, name: 'HAUPT', type: 'program', file_path: 'src/HAUPT.cbl', start_line: 10, source_id: 5 },
    { id: 2, name: 'UNTER', type: 'program', file_path: 'src/UNTER.cbl', start_line: 20, source_id: 5 },
  ],
  edges: [{ id: 100, source: 1, target: 2, type: 'CALL', resolution: 'resolved', target_name: 'UNTER' }],
  truncated: false,
};

const ENTITY = { id: 42, name: 'HAUPT' };

type FetchStub = ReturnType<typeof vi.fn>;

/** fetch-Stub, der Fokus- und Export-Aufrufe getrennt beantwortet. */
function stubFetch(options: {
  focus?: any;
  focusOk?: boolean;
  focusStatus?: number;
  exportOk?: boolean;
  exportStatus?: number;
} = {}): FetchStub {
  const fetchMock = vi.fn(async (url: string) => {
    if (url.includes('/callgraph/export')) {
      return {
        ok: options.exportOk !== false,
        status: options.exportStatus ?? 200,
        blob: async () => new Blob(['export']),
      } as any;
    }
    return {
      ok: options.focusOk !== false,
      status: options.focusStatus ?? 200,
      json: async () => options.focus ?? FOCUS_RESPONSE,
    } as any;
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function renderView(props: Partial<React.ComponentProps<typeof CallGraphView>> = {}) {
  const onFileSelect = vi.fn();
  const view = render(
    <LanguageProvider>
      <CallGraphView theme="dark" focusedEntity={ENTITY} onFileSelect={onFileSelect} {...(props as any)} />
    </LanguageProvider>
  );
  return { ...view, onFileSelect };
}

/** Die URL des zuletzt abgesetzten Fokus-Aufrufs. */
function lastFocusUrl(fetchMock: FetchStub): string {
  const calls = fetchMock.mock.calls.filter(([url]) => String(url).includes('/callgraph/focus'));
  return String(calls[calls.length - 1][0]);
}

function lastExportUrl(fetchMock: FetchStub): string {
  const calls = fetchMock.mock.calls.filter(([url]) => String(url).includes('/callgraph/export'));
  return String(calls[calls.length - 1][0]);
}

describe('CallGraphView', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', ResizeObserverStub);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  describe('Fokus-Laden', () => {
    it('verlangt zuerst einen Fokus und ruft ohne ihn gar nicht erst ab', () => {
      const fetchMock = stubFetch();

      renderView({ focusedEntity: null });

      expect(screen.getByText('Bitte zuerst ein COBOL-Objekt fokussieren.')).toBeTruthy();
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('lädt die Nachbarschaft der fokussierten Entity und rendert sie', async () => {
      const fetchMock = stubFetch();

      renderView();

      await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());
      expect(screen.getByTestId('node-entity:2')).toBeTruthy();
      expect(lastFocusUrl(fetchMock)).toContain('entity_id=42');
      expect(lastFocusUrl(fetchMock)).toContain('hops=1');
    });

    it('schickt den Projektkontext mit, wenn ein Projekt gewählt ist', async () => {
      const fetchMock = stubFetch();

      renderView({ projectId: 7 });

      await waitFor(() => expect(fetchMock).toHaveBeenCalled());
      expect(lastFocusUrl(fetchMock)).toContain('project_id=7');
    });

    it('lässt den Projektparameter im Allgemein-Modus weg', async () => {
      const fetchMock = stubFetch();

      renderView({ projectId: null });

      await waitFor(() => expect(fetchMock).toHaveBeenCalled());
      expect(lastFocusUrl(fetchMock)).not.toContain('project_id');
    });

    it('zeigt den HTTP-Status, wenn der Server den Fokus ablehnt', async () => {
      stubFetch({ focusOk: false, focusStatus: 403 });

      renderView();

      await waitFor(() => expect(screen.getByText('HTTP 403')).toBeTruthy());
    });

    it('fängt einen Netzwerkfehler ab, statt die Ansicht abstürzen zu lassen', async () => {
      vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));

      renderView();

      await waitFor(() => expect(screen.getByText('network down')).toBeTruthy());
    });

    it('ergänzt für eine unaufgelöste Kante einen eigenen Knoten aus dem Zielnamen', async () => {
      stubFetch({
        focus: {
          nodes: [{ id: 1, name: 'HAUPT', type: 'program', file_path: 'src/HAUPT.cbl' }],
          edges: [{ id: 100, source: 1, target: null, type: 'CALL', resolution: 'unresolved', target_name: 'FEHLT' }],
          truncated: false,
        },
      });

      renderView();

      await waitFor(() => expect(screen.getByTestId('node-unresolved:100')).toBeTruthy());
      expect(screen.getByText('FEHLT')).toBeTruthy();
    });

    it('lädt über den Neu-laden-Knopf erneut', async () => {
      const fetchMock = stubFetch();

      renderView();
      await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());
      const before = fetchMock.mock.calls.length;

      fireEvent.click(screen.getByTitle('Neu laden'));

      await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before));
    });

    it('meldet beim Klick auf einen Knoten Datei, Zeile und Quelle nach oben', async () => {
      stubFetch();

      const { onFileSelect } = renderView();
      await waitFor(() => expect(screen.getByTestId('node-entity:2')).toBeTruthy());

      fireEvent.click(screen.getByTestId('node-entity:2'));

      expect(onFileSelect).toHaveBeenCalledWith('src/UNTER.cbl', 20, 5);
    });

    // Der Knoten für ein unaufgelöstes Ziel wird allein aus `target_name`
    // gebaut und hat deshalb gar keinen Dateipfad -- geprüft wird hier also
    // das beobachtbare Verhalten (Klick öffnet nichts), nicht speziell die
    // `!node.unresolved`-Bedingung, die für so einen Knoten ohnehin nie
    // allein den Ausschlag gibt.
    it('öffnet beim Klick auf ein unaufgelöstes Ziel keine Datei', async () => {
      stubFetch({
        focus: {
          nodes: [{ id: 1, name: 'HAUPT', type: 'program', file_path: 'src/HAUPT.cbl' }],
          edges: [{ id: 100, source: 1, target: null, type: 'CALL', resolution: 'unresolved', target_name: 'FEHLT' }],
          truncated: false,
        },
      });

      const { onFileSelect } = renderView();
      await waitFor(() => expect(screen.getByTestId('node-unresolved:100')).toBeTruthy());

      fireEvent.click(screen.getByTestId('node-unresolved:100'));

      expect(onFileSelect).not.toHaveBeenCalled();
    });

    it('blendet über den Kantentyp-Filter Kanten und die daran hängenden Knoten aus', async () => {
      stubFetch();

      renderView();
      await waitFor(() => expect(screen.getByTestId('node-entity:2')).toBeTruthy());

      fireEvent.click(screen.getByRole('button', { name: 'CALL' }));

      await waitFor(() => expect(screen.queryByTestId('node-entity:2')).toBeNull());
      // Nur noch der Fokusknoten selbst -- die Ansicht meldet "keine Verbindungen".
      expect(screen.getByText('Keine Call-Graph-Verbindungen für diesen Fokus.')).toBeTruthy();
    });
  });

  describe('Hops-Auswahl', () => {
    it('lädt bei einer anderen Hop-Zahl neu', async () => {
      const fetchMock = stubFetch();

      renderView();
      await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());

      fireEvent.click(screen.getByRole('button', { name: '3 Hop' }));

      await waitFor(() => expect(lastFocusUrl(fetchMock)).toContain('hops=3'));
    });

    it('hebt die aktive Hop-Zahl hervor', async () => {
      stubFetch();

      renderView();
      await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());

      expect(screen.getByRole('button', { name: '1 Hop' }).className).toContain('border-ds-indigo-500');
      expect(screen.getByRole('button', { name: '2 Hop' }).className).not.toContain('border-ds-indigo-500');

      fireEvent.click(screen.getByRole('button', { name: '2 Hop' }));

      expect(screen.getByRole('button', { name: '2 Hop' }).className).toContain('border-ds-indigo-500');
      expect(screen.getByRole('button', { name: '1 Hop' }).className).not.toContain('border-ds-indigo-500');
    });

    it('beschriftet die Kopfzeile im Singular bzw. Plural', async () => {
      stubFetch();

      renderView();
      await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());

      expect(screen.getByText('Call-Graph · 1 Hop')).toBeTruthy();

      fireEvent.click(screen.getByRole('button', { name: '2 Hop' }));

      expect(screen.getByText('Call-Graph · 2 Hops')).toBeTruthy();
    });
  });

  describe('Export', () => {
    let createdAnchor: HTMLAnchorElement | null;
    let anchorClick: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      createdAnchor = null;
      // jsdom kennt URL.createObjectURL nicht -- die beiden Methoden werden
      // am echten URL-Konstruktor ergaenzt und danach wieder entfernt, damit
      // URL selbst funktionsfaehig bleibt.
      Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:callgraph'), revokeObjectURL: vi.fn() });
      anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
        createdAnchor = this;
      });
    });

    afterEach(() => {
      anchorClick.mockRestore();
      delete (URL as any).createObjectURL;
      delete (URL as any).revokeObjectURL;
    });

    it('bietet alle drei Formate an', async () => {
      stubFetch();

      renderView();
      await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());

      expect(screen.getByRole('button', { name: 'json' })).toBeTruthy();
      expect(screen.getByRole('button', { name: 'csv' })).toBeTruthy();
      expect(screen.getByRole('button', { name: 'graphml' })).toBeTruthy();
    });

    it('lädt den JSON-Export als Datei mit dem Namen der Entity herunter', async () => {
      const fetchMock = stubFetch();

      renderView();
      await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());

      fireEvent.click(screen.getByRole('button', { name: 'json' }));

      await waitFor(() => expect(anchorClick).toHaveBeenCalled());
      expect(lastExportUrl(fetchMock)).toContain('format=json');
      expect(lastExportUrl(fetchMock)).toContain('entity_id=42');
      expect(createdAnchor!.download).toBe('callgraph-HAUPT.json');
      expect(createdAnchor!.href).toContain('blob:callgraph');
    });

    it('benutzt für GraphML die eigene Dateiendung', async () => {
      const fetchMock = stubFetch();

      renderView();
      await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());

      fireEvent.click(screen.getByRole('button', { name: 'graphml' }));

      await waitFor(() => expect(anchorClick).toHaveBeenCalled());
      expect(lastExportUrl(fetchMock)).toContain('format=graphml');
      expect(createdAnchor!.download).toBe('callgraph-HAUPT.graphml');
    });

    it('exportiert mit der gerade gewählten Hop-Zahl und dem Projektkontext', async () => {
      const fetchMock = stubFetch();

      renderView({ projectId: 7 });
      await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());

      fireEvent.click(screen.getByRole('button', { name: '3 Hop' }));
      await waitFor(() => expect(lastFocusUrl(fetchMock)).toContain('hops=3'));

      fireEvent.click(screen.getByRole('button', { name: 'csv' }));

      await waitFor(() => expect(anchorClick).toHaveBeenCalled());
      expect(lastExportUrl(fetchMock)).toContain('hops=3');
      expect(lastExportUrl(fetchMock)).toContain('project_id=7');
    });

    it('zeigt einen Fehler statt eines leeren Downloads, wenn der Export scheitert', async () => {
      stubFetch({ exportOk: false, exportStatus: 500 });

      renderView();
      await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());

      fireEvent.click(screen.getByRole('button', { name: 'json' }));

      await waitFor(() => expect(screen.getByText('Export fehlgeschlagen (HTTP 500)')).toBeTruthy());
      expect(anchorClick).not.toHaveBeenCalled();
    });
  });

  describe('Kapp-Banner', () => {
    it('warnt, wenn der Server die Nachbarschaft gekappt hat', async () => {
      stubFetch({ focus: { ...FOCUS_RESPONSE, truncated: true } });

      renderView();

      await waitFor(() => expect(screen.getByText('Auf 500 Knoten begrenzt')).toBeTruthy());
    });

    it('bleibt still, wenn die Nachbarschaft vollständig ist', async () => {
      stubFetch();

      renderView();

      await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());
      expect(screen.queryByText('Auf 500 Knoten begrenzt')).toBeNull();
    });

    it('nimmt die Warnung zurück, sobald ein Nachladen ungekappt zurückkommt', async () => {
      let truncated = true;
      vi.stubGlobal('fetch', vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ ...FOCUS_RESPONSE, truncated }),
      })));

      renderView();
      await waitFor(() => expect(screen.getByText('Auf 500 Knoten begrenzt')).toBeTruthy());

      truncated = false;
      fireEvent.click(screen.getByTitle('Neu laden'));

      await waitFor(() => expect(screen.queryByText('Auf 500 Knoten begrenzt')).toBeNull());
    });
  });
});
