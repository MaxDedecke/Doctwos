import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { getMermaidRenderConfig, MermaidDiagram } from './MermaidDiagram';

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn().mockResolvedValue({ svg: '<svg viewBox="0 0 100 50"><foreignObject><div xmlns="http://www.w3.org/1999/xhtml">Flow</div></foreignObject></svg>' }),
  },
}));

describe('MermaidDiagram', () => {
  afterEach(() => vi.clearAllMocks());

  it('opens the compact chat diagram in a browser top-layer dialog and closes it with Escape', () => {
    render(<MermaidDiagram code="flowchart TD\nA --> B" theme="dark" />);

    fireEvent.click(screen.getByRole('button', { name: 'Diagramm maximieren' }));

    // jsdom does not implement showModal(), therefore the closed native
    // dialog is not represented in its accessibility tree yet.
    const dialog = document.querySelector<HTMLDialogElement>('dialog[aria-label="Ablaufdiagramm in Großansicht"]');
    if (!dialog) throw new Error('Mermaid dialog was not rendered');
    expect(dialog.parentElement).toBe(document.body);
    expect(dialog.tagName).toBe('DIALOG');
    expect(dialog.className).toContain('z-[3000]');
    expect(screen.getByText('Ablaufdiagramm')).toBeTruthy();

    // Browser Escape dispatches the cancellable `cancel` event on a modal
    // dialog; jsdom does not implement showModal(), so dispatch it directly.
    fireEvent(dialog, new Event('cancel', { bubbles: true, cancelable: true }));

    expect(document.querySelector('dialog[aria-label="Ablaufdiagramm in Großansicht"]')).toBeNull();
  });

  it('disables Mermaid HTML labels globally so flowchart labels use native SVG text', () => {
    expect(getMermaidRenderConfig('dark')).toMatchObject({
      theme: 'dark',
      securityLevel: 'strict',
      htmlLabels: false,
    });
  });
});
