import { axiosResponse } from '@/test/http';
import { api } from '@/app/services/api';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ChatEmptyState } from './ChatEmptyState';

vi.mock('@/app/services/api', () => ({
  api: { getTypingStatement: vi.fn(), getProjectPulse: vi.fn() },
}));

const project = { id: 7, name: 'Kredit' };

function renderEmpty(overrides: Partial<React.ComponentProps<typeof ChatEmptyState>> = {}) {
  const props: React.ComponentProps<typeof ChatEmptyState> = {
    theme: 'dark',
    chatMode: 'evidence',
    selectedProject: null,
    onSend: vi.fn(),
    onFillMessage: vi.fn(),
    addAssistantHint: vi.fn(),
    showToast: vi.fn(),
    ...overrides,
  };
  render(<LanguageProvider><ChatEmptyState {...props} /></LanguageProvider>);
  return props;
}

describe('ChatEmptyState', () => {
  afterEach(() => vi.clearAllMocks());

  it('zeigt im Evidenz-Modus die vier Fachszenarien, im Normal-Modus vier allgemeine', () => {
    vi.mocked(api.getTypingStatement).mockResolvedValue(axiosResponse({ statement: 'x' }));
    const { unmount } = render(
      <LanguageProvider>
        <ChatEmptyState theme="dark" chatMode="evidence" selectedProject={null} onSend={vi.fn()} onFillMessage={vi.fn()} addAssistantHint={vi.fn()} showToast={vi.fn()} />
      </LanguageProvider>
    );
    expect(screen.getByText('COBOL-Programm erklären')).toBeTruthy();
    expect(screen.getByText('Datenfeld finden')).toBeTruthy();
    unmount();

    renderEmpty({ chatMode: 'normal' });
    expect(screen.getByText('Etwas erklären')).toBeTruthy();
    expect(screen.getByText('Ideen sammeln')).toBeTruthy();
    expect(screen.queryByText('COBOL-Programm erklären')).toBeNull();
  });

  it('schneidet Karten und Zähler bei einem Java-Projekt auf Java zu und schimmert statt zu blinken', async () => {
    vi.mocked(api.getProjectPulse).mockResolvedValue(axiosResponse({
      project_id: 7,
      counts: { program: 0, copybook: 0, sql_table: 0, jcl_job: 0, class: 12, interface: 3, method: 90, maven_module: 0 },
      samples: { program: [], copybook: [], sql_table: [], jcl_job: [], class: ['UserLogic'], interface: ['UserService'], method: [], maven_module: [] },
    }));
    renderEmpty({ selectedProject: project as never });

    await waitFor(() => expect(screen.getByText('Klasse erklären')).toBeTruthy());
    expect(screen.getByText('Feld oder Konfiguration finden')).toBeTruthy();
    expect(screen.queryByText('COBOL-Programm erklären')).toBeNull();
    expect(screen.getByText('Klassen')).toBeTruthy();
    expect(screen.queryByText('Programme')).toBeNull();
    expect(document.querySelectorAll('.ds-card-shimmer')).toHaveLength(4);
    expect(document.querySelector('#chat-hint-button-0 .animate-ds-caret')).toBeNull();
  });

  it('tippt im Evidenz-Modus eine Frage mit einem echten Programmnamen aus dem Projekt', async () => {
    vi.mocked(api.getProjectPulse).mockResolvedValue(axiosResponse({
      project_id: 7,
      counts: { program: 1, copybook: 0, sql_table: 0, jcl_job: 0, class: 0, interface: 0, method: 0, maven_module: 0 },
      samples: { program: ['PAYROLL'], copybook: [], sql_table: [], jcl_job: [], class: [], interface: [], method: [], maven_module: [] },
    }));
    renderEmpty({ selectedProject: project as never });

    await waitFor(() => expect(screen.getByRole('heading').textContent).toContain('PAYROLL'), { timeout: 4000 });
    expect(api.getTypingStatement).not.toHaveBeenCalled();
    expect(screen.getByText('Programme')).toBeTruthy();
  });

  it('fällt ohne Projekt-Pulse auf das Backend-Statement zurück', async () => {
    vi.mocked(api.getProjectPulse).mockRejectedValue(new Error('down'));
    vi.mocked(api.getTypingStatement).mockResolvedValue(axiosResponse({ statement: 'Frage' }));
    renderEmpty({ selectedProject: project as never });
    await waitFor(() => expect(screen.getByRole('heading').textContent).toContain('Frage'), { timeout: 3000 });
  });

  it('sendet die getippte Frage über den Pfeil und blendet zuvor nichts ein', async () => {
    vi.mocked(api.getTypingStatement).mockResolvedValue(axiosResponse({ statement: 'Hi' }));
    const props = renderEmpty();
    expect(screen.queryByTitle('Frage direkt stellen')).toBeNull();
    const ask = await screen.findByRole('button', { name: 'Frage direkt stellen' }, { timeout: 3000 });
    fireEvent.click(ask);
    expect(props.onSend).toHaveBeenCalledWith('Hi');
  });

  it('Normal-Karten tragen ihren Satzanfang in die Eingabe ein', () => {
    vi.mocked(api.getTypingStatement).mockResolvedValue(axiosResponse({ statement: 'x' }));
    const props = renderEmpty({ chatMode: 'normal' });
    fireEvent.click(screen.getByText('Etwas erklären'));
    expect(props.onFillMessage).toHaveBeenCalledWith('Erkläre mir bitte einfach, wie ');
  });
});
