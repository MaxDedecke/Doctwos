import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({
    language: 'de',
    t: (key: string, values?: Record<string, string | number>) =>
      values ? `${key}:${Object.values(values).join('/')}` : key,
  }),
}));

import { SYNC_LOG_PAGE_LINES, SyncLogViewer } from './SyncLogViewer';

const makeLog = (count: number) => Array.from({ length: count }, (_, i) => `Zeile ${i + 1}`).join('\n');
const rendered = () => screen.getByTestId('sync-log-scroll').textContent ?? '';

describe('SyncLogViewer', () => {
  it('shows only the newest 200 lines first and offers to load older ones', () => {
    render(<SyncLogViewer log={makeLog(500)} />);

    expect(screen.getByTestId('sync-log-range').textContent).toBe('settings.logsTab.logRange:301/500/500');
    expect(rendered().startsWith('Zeile 301')).toBe(true);
    expect(rendered().endsWith('Zeile 500')).toBe(true);
    expect(rendered()).not.toContain('Zeile 300\n');
    expect(screen.getByText(`settings.logsTab.loadOlder:${SYNC_LOG_PAGE_LINES}`)).toBeTruthy();
  });

  it('loads older lines block by block until the beginning is reached', () => {
    render(<SyncLogViewer log={makeLog(500)} />);

    fireEvent.click(screen.getByText('settings.logsTab.loadOlder:200'));
    expect(screen.getByTestId('sync-log-range').textContent).toBe('settings.logsTab.logRange:101/500/500');
    expect(rendered().startsWith('Zeile 101')).toBe(true);

    fireEvent.click(screen.getByText('settings.logsTab.loadOlder:100'));
    expect(screen.getByTestId('sync-log-range').textContent).toBe('settings.logsTab.logRange:1/500/500');
    expect(rendered().startsWith('Zeile 1\n')).toBe(true);
    expect(screen.queryByText(/settings\.logsTab\.loadOlder/)).toBeNull();
  });

  it('loads older lines automatically when scrolled to the top', () => {
    render(<SyncLogViewer log={makeLog(500)} />);
    const scroll = screen.getByTestId('sync-log-scroll');

    fireEvent.scroll(scroll, { target: { scrollTop: 0 } });

    expect(screen.getByTestId('sync-log-range').textContent).toBe('settings.logsTab.logRange:101/500/500');
  });

  it('keeps the loaded window when new lines arrive while polling', () => {
    const { rerender } = render(<SyncLogViewer log={makeLog(500)} />);
    fireEvent.click(screen.getByText('settings.logsTab.loadOlder:200'));

    rerender(<SyncLogViewer log={makeLog(510)} />);

    // Das Fenster wächst nur nach unten; die zuvor nachgeladenen Zeilen bleiben stehen.
    expect(screen.getByTestId('sync-log-range').textContent).toBe('settings.logsTab.logRange:101/510/510');
    expect(rendered().startsWith('Zeile 101')).toBe(true);
    expect(rendered().endsWith('Zeile 510')).toBe(true);
  });

  it('follows the tail while nothing older was loaded', () => {
    const { rerender } = render(<SyncLogViewer log={makeLog(500)} />);
    rerender(<SyncLogViewer log={makeLog(520)} />);
    expect(screen.getByTestId('sync-log-range').textContent).toBe('settings.logsTab.logRange:321/520/520');
  });

  it('clamps the window when the log restarts and becomes shorter', () => {
    const { rerender } = render(<SyncLogViewer log={makeLog(500)} />);
    fireEvent.click(screen.getByText('settings.logsTab.loadOlder:200'));
    rerender(<SyncLogViewer log={makeLog(30)} />);
    expect(screen.getByTestId('sync-log-range').textContent).toBe('settings.logsTab.logRange:1/30/30');
  });

  it('shows a short log completely without a load-older button', () => {
    render(<SyncLogViewer log={makeLog(12)} />);
    expect(screen.getByTestId('sync-log-range').textContent).toBe('settings.logsTab.logRange:1/12/12');
    expect(screen.queryByText(/settings\.logsTab\.loadOlder/)).toBeNull();
  });

  it('shows the placeholder for an empty log', () => {
    render(<SyncLogViewer log="" />);
    expect(screen.getByText('settings.logsTab.noLogsPlaceholder')).toBeTruthy();
    expect(screen.queryByTestId('sync-log-viewer')).toBeNull();
  });
});
