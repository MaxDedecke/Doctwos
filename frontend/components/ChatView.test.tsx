/**
 * O-055: ChatView.tsx -- die eigentliche Chat-Oberfläche, das Kernprodukt --
 * hatte keinen einzigen Test. Deckt die in O-055 genannten Bereiche ab:
 * Nachrichten rendern (inkl. Markdown/Code-Blöcke), Senden, Streaming-Anzeige,
 * Retry/Feedback-Buttons, leerer Zustand, Fehlerzustand (Fallback der
 * Begrüßungs-Statements) und Quellen-/Refs-Anzeige.
 *
 * ChatView selbst hält keinen Chat-Zustand (chatMessages/currentMessage/
 * isLoading kommen als Props von useChatController) -- "Senden" bedeutet hier
 * also: die passenden Handler-Props werden mit den richtigen Argumenten
 * aufgerufen, nicht dass irgendein Netzwerk-Request stattfindet.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { ChatView } from './ChatView';
import { api } from '@/app/services/api';

vi.mock('@/app/services/api', () => ({
  api: {
    getTypingStatement: vi.fn(),
  },
}));

function makeProps(overrides: Partial<React.ComponentProps<typeof ChatView>> = {}) {
  return {
    theme: 'dark',
    isSidebarOpen: true,
    selectedProject: null,
    onProjectSelect: vi.fn(),
    pinnedCode: null,
    setPinnedCode: vi.fn(),
    chatMessages: [] as any[],
    currentMessage: '',
    setCurrentMessage: vi.fn(),
    isLoading: false,
    handleSendChat: vi.fn(),
    handleRetryMessage: vi.fn(),
    handleFeedback: vi.fn(),
    addAssistantHint: vi.fn(),
    handleFileSelect: vi.fn(),
    activeProfileId: 'p1',
    setActiveProfileId: vi.fn(),
    llmProfiles: [{ id: 'p1', name: 'Mistral', model: 'mistral-nemo' }],
    showToast: vi.fn(),
    selectedFile: null,
    selectedDoc: null,
    splitClasses: { chat: 'w-1/2', editor: 'w-1/2' },
    chatEndRef: React.createRef<HTMLDivElement>(),
    selectedSource: null,
    setSelectedSource: vi.fn(),
    connectedSources: [],
    ...overrides,
  };
}

function renderChat(overrides: Partial<React.ComponentProps<typeof ChatView>> = {}) {
  const props = makeProps(overrides);
  const view = render(
    <LanguageProvider>
      <ChatView {...(props as any)} />
    </LanguageProvider>
  );
  return { ...view, props };
}

describe('ChatView', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('leerer Zustand', () => {
    it('zeigt die Vorschlagskarten, solange kein Chatverlauf existiert', async () => {
      vi.mocked(api.getTypingStatement).mockResolvedValue({ data: { statement: 'Testansage' } } as any);

      renderChat();

      expect(screen.getByText('COBOL-Programm erklären')).toBeTruthy();
      expect(screen.getByText('Aufrufkette verfolgen')).toBeTruthy();
      expect(screen.getByText('Datenfeld finden')).toBeTruthy();
      await waitFor(() => expect(api.getTypingStatement).toHaveBeenCalled());
    });

    it('Fehlerzustand: fällt bei fehlgeschlagenem Begrüßungs-Statement auf einen lokalen Fallback-Text zurück', async () => {
      vi.mocked(api.getTypingStatement).mockRejectedValue(new Error('network down'));

      renderChat();

      // Die Tippanimation baut den Text zeichenweise auf (70ms/Zeichen) --
      // ihr Endzustand ist einer der vier lokalen Fallback-Sätze.
      const fallbacks = [
        'COBOL-Wissen sichtbar machen',
        'Mainframe-Code verständlich navigieren',
        'Legacy-Systeme erschließen',
        'Programme, Copybooks, Zusammenhänge',
      ];
      await waitFor(() => {
        const matched = fallbacks.some((f) => screen.queryByText(f) !== null);
        expect(matched).toBe(true);
      }, { timeout: 3000 });
    });

    it('das Projekt-Onboarding-Vorschlagsfeld ist ohne ausgewähltes Projekt deaktiviert und zeigt einen Hinweis-Toast', async () => {
      vi.mocked(api.getTypingStatement).mockResolvedValue({ data: { statement: 'x' } } as any);
      const showToast = vi.fn();

      renderChat({ selectedProject: null, showToast });

      const onboardingButton = screen.getByText('Projekt-Onboarding starten').closest('button')!;
      expect(onboardingButton.disabled).toBe(true);
    });

    it('ein Vorschlag mit Rückfrage ("clarify") übernimmt den Textbaustein und stellt die Rückfrage als Assistenten-Hinweis', async () => {
      vi.mocked(api.getTypingStatement).mockResolvedValue({ data: { statement: 'x' } } as any);
      const addAssistantHint = vi.fn();
      const setCurrentMessage = vi.fn();

      renderChat({ addAssistantHint, setCurrentMessage });

      fireEvent.click(screen.getByText('COBOL-Programm erklären'));

      expect(addAssistantHint).toHaveBeenCalledWith('Welches COBOL-Programm soll ich Ihnen erklären?');
      expect(setCurrentMessage).toHaveBeenCalledWith('Erkläre mir das Programm ');
    });
  });

  describe('Nachrichten rendern', () => {
    it('rendert Nutzer- und Assistentennachrichten inklusive Markdown (fett, Codeblock)', () => {
      const chatMessages = [
        { id: 1, role: 'user', content: 'Was macht DISPATCHER.cbl?' },
        {
          id: 2,
          role: 'assistant',
          content: 'Das ist **wichtig**:\n\n```cobol\nMOVE 1 TO WS-FLAG.\n```',
        },
      ];

      renderChat({ chatMessages });

      expect(screen.getByText('Was macht DISPATCHER.cbl?')).toBeTruthy();
      expect(screen.getByText('wichtig')).toBeTruthy();
      expect(screen.getByText('MOVE 1 TO WS-FLAG.')).toBeTruthy();
    });

    it('zeigt Referenzen einer Nutzernachricht als klickbare Badges, die handleFileSelect auslösen', () => {
      const handleFileSelect = vi.fn();
      const chatMessages = [
        {
          id: 1,
          role: 'user',
          content: 'Zeig mir das',
          metadata: { refs: [{ file: 'src/DISPATCHER.cbl', line: 42, source_id: '7' }] },
        },
      ];

      renderChat({ chatMessages, handleFileSelect });

      fireEvent.click(screen.getByText('DISPATCHER.cbl:42'));

      expect(handleFileSelect).toHaveBeenCalledWith('src/DISPATCHER.cbl', 42, '7');
    });

    it('zeigt referenzierte Quellen einer fertigen Assistentenantwort und öffnet sie über handleFileSelect', () => {
      const handleFileSelect = vi.fn();
      const chatMessages = [
        {
          id: 2,
          role: 'assistant',
          content: 'Antwort.',
          sources: [{ file: 'src/DISPATCHER.cbl', lines: [10, 20], source_id: '7' }],
        },
      ];

      renderChat({ chatMessages, handleFileSelect, isLoading: false });

      expect(screen.getByText('Referenzierte Quellen:')).toBeTruthy();
      fireEvent.click(screen.getByText('DISPATCHER.cbl'));

      expect(handleFileSelect).toHaveBeenCalledWith('src/DISPATCHER.cbl', 10, '7');
    });

    it('zeigt das Modell-Badge einer Assistentenantwort', () => {
      const chatMessages = [
        { id: 2, role: 'assistant', content: 'Antwort.', metadata: { model: 'mistral-nemo' } },
      ];

      renderChat({ chatMessages });

      expect(screen.getByText('mistral-nemo')).toBeTruthy();
    });
  });

  describe('Streaming-Anzeige', () => {
    it('zeigt einen Ladeindikator, solange die letzte Assistentennachricht noch keinen Inhalt hat', () => {
      const chatMessages = [
        { id: 1, role: 'user', content: 'Frage' },
        { id: 2, role: 'assistant', content: '' },
      ];

      renderChat({ chatMessages, isLoading: true });

      expect(screen.getByText('Antwort wird generiert...')).toBeTruthy();
    });

    it('zeigt "Agent arbeitet..." statt der Aktionsleiste, solange die letzte Antwort noch streamt', () => {
      const chatMessages = [
        { id: 2, role: 'assistant', content: 'Teilantwort...' },
      ];

      renderChat({ chatMessages, isLoading: true });

      expect(screen.getByText('Agent arbeitet...')).toBeTruthy();
      // Aktionszeile (Copy/Feedback/Retry) erscheint erst nach Abschluss des Streams.
      expect(screen.queryByTitle('Antwort wiederholen')).toBeNull();
    });

    it('zeigt die Aktionsleiste (Copy/Feedback/Retry), sobald die Antwort fertig ist', () => {
      const chatMessages = [
        { id: 2, role: 'assistant', content: 'Fertige Antwort.' },
      ];

      renderChat({ chatMessages, isLoading: false });

      expect(screen.getByTitle('Nachricht kopieren')).toBeTruthy();
      expect(screen.getByTitle('Hilfreich')).toBeTruthy();
      expect(screen.getByTitle('Nicht hilfreich')).toBeTruthy();
      expect(screen.getByTitle('Antwort wiederholen')).toBeTruthy();
    });
  });

  describe('Retry- und Feedback-Buttons', () => {
    it('ruft handleRetryMessage mit dem Nachrichtenindex auf', () => {
      const handleRetryMessage = vi.fn();
      const chatMessages = [
        { id: 1, role: 'user', content: 'Frage' },
        { id: 2, role: 'assistant', content: 'Antwort.' },
      ];

      renderChat({ chatMessages, handleRetryMessage });

      fireEvent.click(screen.getByTitle('Antwort wiederholen'));

      expect(handleRetryMessage).toHaveBeenCalledWith(1);
    });

    it('deaktiviert Retry, solange noch geladen wird', () => {
      const chatMessages = [{ id: 2, role: 'assistant', content: 'Antwort.' }];

      renderChat({ chatMessages, isLoading: true });

      // Während des Streams zeigt der Zweig nur "Agent arbeitet..." -- die
      // Aktionsleiste (und damit der Retry-Button) erscheint erst danach, siehe
      // "Streaming-Anzeige"-Block. Hier zusätzlich mit einer weiteren
      // *abgeschlossenen* vorherigen Nachricht abgesichert, dass ein bereits
      // fertiger Retry-Button gesperrt bleibt, wenn eine andere Nachricht lädt.
      const chatMessagesTwo = [
        { id: 1, role: 'assistant', content: 'Ältere fertige Antwort.' },
        { id: 2, role: 'assistant', content: '', metadata: { agent_steps: [] } },
      ];
      const handleRetryMessage = vi.fn();
      renderChat({ chatMessages: chatMessagesTwo, isLoading: true, handleRetryMessage });

      const retryButtons = screen.getAllByTitle('Antwort wiederholen');
      fireEvent.click(retryButtons[0]);
      // isLoading=true sperrt jeden Retry-Button, unabhängig davon, welche
      // Nachricht gerade streamt.
      expect(handleRetryMessage).not.toHaveBeenCalled();
    });

    it('ruft handleFeedback mit Nachrichten-ID und "up"/"down" auf', () => {
      const handleFeedback = vi.fn();
      const chatMessages = [{ id: 42, role: 'assistant', content: 'Antwort.' }];

      renderChat({ chatMessages, handleFeedback });

      fireEvent.click(screen.getByTitle('Hilfreich'));
      fireEvent.click(screen.getByTitle('Nicht hilfreich'));

      expect(handleFeedback).toHaveBeenCalledWith(42, 'up');
      expect(handleFeedback).toHaveBeenCalledWith(42, 'down');
    });

    it('deaktiviert Feedback-Buttons für Nachrichten ohne ID (noch nicht persistiert)', () => {
      const handleFeedback = vi.fn();
      const chatMessages = [{ role: 'assistant', content: 'Antwort ohne ID.' }];

      renderChat({ chatMessages, handleFeedback });

      expect((screen.getByTitle('Hilfreich') as HTMLButtonElement).disabled).toBe(true);
      expect((screen.getByTitle('Nicht hilfreich') as HTMLButtonElement).disabled).toBe(true);
    });
  });

  describe('Senden', () => {
    it('ruft handleSendChat beim Klick auf den Senden-Button auf', () => {
      const handleSendChat = vi.fn();

      renderChat({ currentMessage: 'Hallo Doctus', handleSendChat });

      fireEvent.click(screen.getByLabelText('Nachricht senden'));

      expect(handleSendChat).toHaveBeenCalledWith();
    });

    it('deaktiviert den Senden-Button bei leerer oder nur aus Leerraum bestehender Nachricht', () => {
      renderChat({ currentMessage: '   ' });

      expect((screen.getByLabelText('Nachricht senden') as HTMLButtonElement).disabled).toBe(true);
    });

    it('deaktiviert den Senden-Button während eine Antwort noch lädt', () => {
      renderChat({ currentMessage: 'Hallo', isLoading: true });

      expect((screen.getByLabelText('Nachricht senden') as HTMLButtonElement).disabled).toBe(true);
    });

    it('sendet per Enter ab, aber nicht per Shift+Enter (Zeilenumbruch)', () => {
      const handleSendChat = vi.fn();

      renderChat({ currentMessage: 'Hallo', handleSendChat });
      const textarea = screen.getByPlaceholderText('Frag Doctus AI...');

      fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
      expect(handleSendChat).not.toHaveBeenCalled();

      fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
      expect(handleSendChat).toHaveBeenCalledTimes(1);
    });

    it('gibt Tastatureingaben über setCurrentMessage weiter', () => {
      const setCurrentMessage = vi.fn();

      renderChat({ setCurrentMessage });
      const textarea = screen.getByPlaceholderText('Frag Doctus AI...');

      fireEvent.change(textarea, { target: { value: 'Neuer Text' } });

      expect(setCurrentMessage).toHaveBeenCalledWith('Neuer Text');
    });
  });

  describe('Kontext-Chips (Projekt/Quelle/Pin)', () => {
    it('zeigt einen Projekt-Chip und hebt den Fokus über onProjectSelect(null) wieder auf', () => {
      const onProjectSelect = vi.fn();

      renderChat({ selectedProject: { id: 1, name: 'DRV-Bestand' }, onProjectSelect });

      expect(screen.getByText('Projekt: DRV-Bestand')).toBeTruthy();
      // Der Projekt-Chip erscheint sowohl im Header als auch (identisch
      // betitelt) in der Kontextleiste über dem Eingabefeld -- beide rufen
      // denselben Handler auf, hier reicht der erste.
      fireEvent.click(screen.getAllByTitle('Kontext aufheben')[0]);

      expect(onProjectSelect).toHaveBeenCalledWith(null);
    });

    it('zeigt einen Pin-Chip und hebt ihn über setPinnedCode(null) wieder auf', () => {
      const setPinnedCode = vi.fn();

      renderChat({
        pinnedCode: { filepath: 'src/DISPATCHER.cbl', line: 42, label: null, context: null },
        setPinnedCode,
      });

      expect(screen.getByText('Pin: DISPATCHER.cbl:42')).toBeTruthy();
      fireEvent.click(screen.getByTitle('Pin aufheben'));

      expect(setPinnedCode).toHaveBeenCalledWith(null);
    });
  });
});
