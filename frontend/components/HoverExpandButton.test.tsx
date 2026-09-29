import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HoverExpandButton, expandedWidthPx } from './HoverExpandButton';

const renderButton = (props: Partial<React.ComponentProps<typeof HoverExpandButton>> = {}) =>
  render(<HoverExpandButton tone="indigo" icon={<svg data-testid="icon" />} label="Änderung untersuchen" onClick={vi.fn()} {...props} />);

describe('HoverExpandButton', () => {
  it('is collapsed to a small icon button by default and expands on hover or keyboard focus', () => {
    renderButton();
    const button = screen.getByRole('button', { name: 'Änderung untersuchen' });

    expect(button.className).toContain('w-7');
    expect(button.className).toContain('hover:w-[var(--expand-w)]');
    expect(button.className).toContain('focus-visible:w-[var(--expand-w)]');
    expect(button.className).toContain('transition-[width');
  });

  it('keeps the full label available to assistive technology and tests while it is collapsed', () => {
    renderButton();
    expect(screen.getByText('Änderung untersuchen').className).toContain('opacity-0');
    expect(screen.getByRole('button', { name: 'Änderung untersuchen' }).getAttribute('aria-label')).toBe('Änderung untersuchen');
  });

  it('sizes the expanded width from the label so it fits in any language', () => {
    expect(expandedWidthPx('Erkenntnis sichern')).toBeLessThan(expandedWidthPx('Änderung untersuchen'));
    renderButton({ label: 'Investigate change' });
    const button = screen.getByRole('button', { name: 'Investigate change' });
    expect(button.style.getPropertyValue('--expand-w')).toBe(`${expandedWidthPx('Investigate change')}px`);
  });

  it('uses an explicit title and forwards clicks and the test id', () => {
    const onClick = vi.fn();
    renderButton({ onClick, title: 'Impact-Paket', testId: 'investigate-change' });

    fireEvent.click(screen.getByTestId('investigate-change'));

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('investigate-change').getAttribute('title')).toBe('Impact-Paket');
  });

  it('does not expand or fire when disabled', () => {
    const onClick = vi.fn();
    renderButton({ onClick, disabled: true });
    const button = screen.getByRole('button', { name: 'Änderung untersuchen' }) as HTMLButtonElement;

    fireEvent.click(button);

    expect(button.disabled).toBe(true);
    expect(button.className).toContain('disabled:hover:w-7');
    expect(onClick).not.toHaveBeenCalled();
  });

  it('colors the amber and indigo variants differently', () => {
    const { unmount } = renderButton({ tone: 'amber' });
    expect(screen.getByRole('button').className).toContain('border-ds-amber-500/60');
    unmount();
    renderButton({ tone: 'indigo' });
    expect(screen.getByRole('button').className).toContain('border-ds-indigo-500/60');
  });
});
