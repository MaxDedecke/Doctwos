import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RevealedMarkdown } from './RevealedMarkdown';

vi.mock('@/components/MarkdownContent', () => ({
  MarkdownContent: ({ content }: { content: string }) => <div data-testid="markdown">{content}</div>,
}));

const answer = Array.from({ length: 400 }, (_, i) => `wort${i}`).join(' ');
const noop = () => {};
const shownLength = () => screen.getByTestId('markdown').textContent?.length ?? 0;

describe('RevealedMarkdown', () => {
  beforeEach(() => { vi.useFakeTimers({ toFake: ['requestAnimationFrame', 'cancelAnimationFrame', 'performance'] }); });
  afterEach(() => { vi.useRealTimers(); });

  it('reveals an answer that arrives in one block and finishes after the request has ended', () => {
    const { rerender } = render(<RevealedMarkdown live content="" theme="dark" onFileClick={noop} />);
    rerender(<RevealedMarkdown live content={answer} theme="dark" onFileClick={noop} />);
    act(() => { vi.advanceTimersByTime(100); });
    expect(shownLength()).toBeGreaterThan(0);
    expect(shownLength()).toBeLessThan(answer.length);

    // Die Antwort kommt mit dem Ende des Streams; das Einblenden läuft trotzdem weiter.
    rerender(<RevealedMarkdown live={false} content={answer} theme="dark" onFileClick={noop} />);
    expect(shownLength()).toBeLessThan(answer.length);
    act(() => { vi.advanceTimersByTime(2500); });
    expect(shownLength()).toBe(answer.length);
  });

  it('shows a saved answer at once, also after switching to another session', () => {
    const { rerender } = render(<RevealedMarkdown live={false} content={answer} theme="dark" onFileClick={noop} />);
    expect(shownLength()).toBe(answer.length);
    rerender(<RevealedMarkdown live={false} content="Eine ganz andere gespeicherte Antwort." theme="dark" onFileClick={noop} />);
    expect(screen.getByTestId('markdown').textContent).toBe('Eine ganz andere gespeicherte Antwort.');
  });
});
