import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ChatComposer, type ChatComposerProps } from './ChatComposer';

vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({ t: (key: string) => key, language: 'de' }),
}));

function props(overrides: Partial<ChatComposerProps> = {}): ChatComposerProps {
  return {
    theme: 'dark', currentMessage: '', setCurrentMessage: vi.fn(), handleSendChat: vi.fn(), isLoading: false,
    onStop: vi.fn(), editing: false, canEditLast: true, onEditLast: vi.fn(), onCancelEdit: vi.fn(),
    selectedProject: null, selectedSource: null, setSelectedSource: vi.fn(), pinnedCode: null, setPinnedCode: vi.fn(),
    filteredSources: [], handleSourceFocusChange: vi.fn(), sessionChatMode: null, activeChatMode: 'evidence',
    activeProfileId: '1', setActiveProfileId: vi.fn(),
    llmProfiles: [{ id: '1', name: 'Lokal', provider: 'ollama', model: 'qwen3:8b', capabilities: { tools: false } }],
    showToast: vi.fn(), ...overrides,
  };
}

describe('ChatComposer', () => {
  it('turns send into stop while an answer runs, also via Esc', () => {
    const onStop = vi.fn();
    render(<ChatComposer {...props({ isLoading: true, onStop })} />);

    fireEvent.click(screen.getByRole('button', { name: 'chatView.stopAnswer' }));
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' });

    expect(onStop).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('button', { name: 'chatView.sendMessageLabel' })).toBeNull();
  });

  it('recalls the last question with arrow up in an empty field and shows the editing chip', () => {
    const onEditLast = vi.fn();
    const { rerender } = render(<ChatComposer {...props({ onEditLast })} />);
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'ArrowUp' });
    expect(onEditLast).toHaveBeenCalled();

    const onCancelEdit = vi.fn();
    rerender(<ChatComposer {...props({ editing: true, currentMessage: 'Frage', onCancelEdit })} />);
    expect(screen.getByText('chatView.editingQuestion')).toBeTruthy();
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' });
    expect(onCancelEdit).toHaveBeenCalled();
  });
});

describe('ChatComposer mentions', () => {
  it('suggests code objects after @ and inserts the chosen name', async () => {
    const { api } = await import('@/app/services/api');
    const { axiosResponse } = await import('@/test/http');
    vi.spyOn(api, 'searchGlobal').mockResolvedValue(axiosResponse({ results: [
      { node_type: 'entity', node_id: 5, node_label: 'COSGN00C', node_url: null, node_meta: { type: 'program', file_path: 'app/cbl/COSGN00C.cbl' } },
    ], total: 1, counts: {} }) as never);
    const setCurrentMessage = vi.fn();
    render(<ChatComposer {...props({ currentMessage: 'Wer ruft @COS', setCurrentMessage, selectedProject: { id: 1, name: 'CardDemo' } })} />);
    const field = screen.getByRole('textbox') as HTMLTextAreaElement;
    field.setSelectionRange(13, 13);
    fireEvent.select(field);

    const option = await screen.findByRole('option', {}, { timeout: 2000 });
    fireEvent.mouseDown(option);

    expect(setCurrentMessage).toHaveBeenCalledWith('Wer ruft `COSGN00C` ');
  });
});

describe('ChatComposer attachments', () => {
  it('attaches a dropped text file and sends it with the question', async () => {
    const handleSendChat = vi.fn();
    render(<ChatComposer {...props({ currentMessage: 'Was heißt das?', handleSendChat })} />);
    const file = new File(['IEF450I ABEND=S0C7'], 'job.log', { type: 'text/plain' });

    fireEvent.drop(screen.getByRole('textbox').parentElement as HTMLElement, { dataTransfer: { files: [file], types: ['Files'] } });
    await screen.findByText('job.log');
    fireEvent.click(screen.getByRole('button', { name: 'chatView.sendMessageLabel' }));

    expect(handleSendChat).toHaveBeenCalledWith([{ name: 'job.log', content: 'IEF450I ABEND=S0C7' }]);
    expect(screen.queryByText('job.log')).toBeNull();
  });
});
