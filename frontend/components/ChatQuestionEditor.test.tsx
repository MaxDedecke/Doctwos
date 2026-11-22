import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ChatQuestionEditor } from './ChatQuestionEditor';

vi.mock('@/lib/i18n/LanguageContext', () => ({ useLanguage: () => ({ t: (key: string) => key, language: 'de' }) }));

describe('ChatQuestionEditor', () => {
  it('sends the edited question with Enter and cancels with Escape', () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();
    render(<ChatQuestionEditor initial="Alte Frage" theme="dark" onSubmit={onSubmit} onCancel={onCancel} />);
    const field = screen.getByRole('textbox', { name: 'chatView.editQuestion' });

    fireEvent.change(field, { target: { value: 'Neue Frage ' } });
    fireEvent.keyDown(field, { key: 'Enter' });
    expect(onSubmit).toHaveBeenCalledWith('Neue Frage');

    fireEvent.keyDown(field, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalled();
  });
});
