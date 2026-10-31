import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { FocusIndicator } from './FocusIndicator';
import type { CodeEntity } from '@/types/domain';

const nothing = { selectedEntity: null, selectedDoc: null, selectedFile: null };
const renderIndicator = (selection: Partial<typeof nothing> | object, onView = vi.fn(), onClear = vi.fn()) => {
  const { container } = render(
    <LanguageProvider>
      <FocusIndicator selection={{ ...nothing, ...selection }} theme="dark" onView={onView} onClear={onClear} />
    </LanguageProvider>,
  );
  return { container, onView, onClear };
};

describe('FocusIndicator', () => {
  it('shows nothing without a focus', () => {
    expect(renderIndicator({}).container.firstChild).toBeNull();
  });

  it('shows an object by name and readable kind, and its path on hover', async () => {
    const entity = { id: 1, name: 'poll', type: 'method', file_path: 'src/app/KafkaConsumer.java' } as CodeEntity;
    const { onView, onClear } = renderIndicator({ selectedEntity: entity, selectedFile: entity.file_path });

    expect(screen.getByText('poll')).toBeTruthy();
    const trigger = screen.getByRole('button', { name: /poll/ });
    fireEvent.mouseEnter(trigger);
    expect(await screen.findByText('src/app/KafkaConsumer.java')).toBeTruthy();

    fireEvent.click(trigger);
    expect(onView).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getAllByRole('button').find((button) => button.getAttribute('title'))!);
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it('shortens a file to its name and a document path too', () => {
    renderIndicator({ selectedFile: 'src/app/ZAHLUNG.cbl' });
    expect(screen.getByText('ZAHLUNG.cbl')).toBeTruthy();
  });

  it('prefers the document when no object is focused', () => {
    renderIndicator({ selectedDoc: { id: 3, name: 'docs/Betrieb.md' } });
    expect(screen.getByText('Betrieb.md')).toBeTruthy();
  });
});
