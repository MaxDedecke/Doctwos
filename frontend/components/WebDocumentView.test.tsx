import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import type { WebDocumentData } from '@/lib/webDocumentHtml';
import { WebDocumentView } from './WebDocumentView';

const DOC: WebDocumentData = {
  title: 'Fehler <b>x</b>', url: 'https://jira/browse/A-1', kind: 'ticket', identifier: 'A-1',
  facts: [
    { key: 'status', label: 'Status', values: ['Open'], kind: 'status' },
    { key: 'labels', label: 'Labels', values: ['cobol', 'batch'], kind: 'text' },
    { key: 'risk_class', label: 'Risk class', values: ['hoch'], kind: 'text' },
    { key: 'created', label: 'Created', values: ['2026-01-02T10:00:00Z'], kind: 'date' },
  ],
  breadcrumbs: [{ title: 'Bekannt', url: 'https://w/1', source_id: 3 }, { title: 'Fremd', url: 'https://w/2' }, { title: 'Ohne' }],
  body_html: '<p>Inhalt</p>', comments: [], attachments: [{ name: 'log.txt', url: '/knowledge-sources/1/web-asset?token=t', size: 2048 }],
  related: [
    { relation: 'parent', title: 'Oben', url: 'https://jira/browse/A-0', identifier: 'A-0', source_id: 1 },
    { relation: 'blocks', title: 'Extern', url: 'https://jira/browse/X-9', identifier: 'X-9', status: 'Done' },
  ],
  extra_css: '', origin: 'live',
};

const show = (doc: WebDocumentData = DOC, onOpenKnown = vi.fn()) => {
  render(<LanguageProvider><WebDocumentView document={doc} theme="dark" onOpenKnown={onOpenKnown} /></LanguageProvider>);
  return onOpenKnown;
};

describe('WebDocumentView', () => {
  it('shows metadata as text, translates known facts and uses the system label for unknown ones', () => {
    show();
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('A-1Fehler <b>x</b>');
    expect(screen.getByText('Open')).toBeTruthy();
    expect(screen.getByText('cobol')).toBeTruthy();
    expect(screen.getByText('Risk class:')).toBeTruthy();
    expect(screen.queryByText('2026-01-02T10:00:00Z')).toBeNull();
  });

  it('opens known entries in Doctus and leaves the rest as links', () => {
    const onOpenKnown = show();
    fireEvent.click(screen.getByRole('button', { name: 'Bekannt' }));
    expect(onOpenKnown).toHaveBeenCalledWith('https://w/1', 3);
    fireEvent.click(screen.getByRole('button', { name: /A-0/ }));
    expect(onOpenKnown).toHaveBeenCalledWith('https://jira/browse/A-0', 1);
    expect(screen.getByRole('link', { name: 'Fremd' }).getAttribute('target')).toBe('_blank');
    expect(screen.getByRole('link', { name: /X-9/ }).getAttribute('href')).toBe('https://jira/browse/X-9');
  });

  it('points attachments at the API and keeps the content sandboxed without same-origin', () => {
    show();
    expect(screen.getByRole('link', { name: 'log.txt' }).getAttribute('href')).toContain('/knowledge-sources/1/web-asset?token=t');
    const frame = screen.getByTitle('Fehler <b>x</b>');
    expect(frame.getAttribute('sandbox')).not.toContain('allow-same-origin');
    expect(frame.getAttribute('srcdoc')).toContain('<p>Inhalt</p>');
  });

  it('names the fallback to the index with its date', () => {
    show({ ...DOC, origin: 'index', notice: 'unreachable', synced_at: '2026-03-01T10:00:00Z' });
    expect(screen.getByRole('status').textContent).toMatch(/nicht erreichbar.*Stand/);
  });

  it('accepts link messages only from its own frame and with a numeric source', () => {
    const onOpenKnown = show();
    const frame = screen.getByTitle('Fehler <b>x</b>') as HTMLIFrameElement;
    const message = (source: unknown, data: unknown) => window.dispatchEvent(new MessageEvent('message', { source: source as MessageEventSource, data }));
    message(window, { type: 'doctus-web-link', url: 'https://x', sourceId: '1' });
    message(frame.contentWindow, { type: 'other', url: 'https://x', sourceId: '1' });
    message(frame.contentWindow, { type: 'doctus-web-link', url: 'https://x', sourceId: 'evil' });
    expect(onOpenKnown).not.toHaveBeenCalled();
    message(frame.contentWindow, { type: 'doctus-web-link', url: 'https://x', sourceId: '4' });
    expect(onOpenKnown).toHaveBeenCalledWith('https://x', 4);
  });
});
