import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ChatMessageActions } from './ChatMessageActions';
import type { ChatMessage } from '@/types/domain';

vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({ t: (key: string) => key, language: 'de' }),
}));
vi.mock('@/components/InsightDraftAction', () => ({ InsightDraftAction: () => null }));

const message: ChatMessage = {
  id: 20, role: 'assistant', content: 'Neu',
  metadata: { model: 'qwen', versions: [{ content: 'Alt 1' }, { content: 'Alt 2' }], telemetry: { events: [], metrics: { response_time_ms: 3800, first_token_ms: null, tool_count: 0, retrieval_wait_ms: null, first_tool_call_ms: null, model_end_ms: null } } },
};

function renderActions(overrides: Partial<Parameters<typeof ChatMessageActions>[0]> = {}) {
  const props = {
    message, index: 1, theme: 'dark', isLoading: false, showOriginal: false, onToggleOriginal: vi.fn(),
    onFeedback: vi.fn(), onRetry: vi.fn(), selectedProject: null, showToast: vi.fn(),
    versionIndex: 2, onVersionChange: vi.fn(), ...overrides,
  };
  render(<ChatMessageActions {...props} />);
  return props;
}

describe('ChatMessageActions', () => {
  it('switches between answer versions and shows the response time', () => {
    const props = renderActions();

    expect(screen.getByText('3/3')).toBeTruthy();
    expect(screen.getByText(/3,8 s/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'chatView.previousVersion' }));
    expect(props.onVersionChange).toHaveBeenCalledWith(1);
  });

  it('asks for a reason after a downvote and sends it', () => {
    const props = renderActions();

    fireEvent.click(screen.getByTitle('chatView.notHelpfulTitle'));
    expect(props.onFeedback).toHaveBeenCalledWith(20, 'down');
    fireEvent.click(screen.getByRole('button', { name: 'chatView.feedbackReason.wrong_source' }));
    fireEvent.click(screen.getByRole('button', { name: 'chatView.feedbackReason.send' }));

    expect(props.onFeedback).toHaveBeenLastCalledWith(20, 'down', 'wrong_source', undefined);
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
