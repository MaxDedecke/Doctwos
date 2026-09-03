/**
 * Regressionstest: der Chat-Panel-Einklapp-Mechanismus ("Chat einklappen"/
 * "Chat ausklappen") ist ein Relikt aus der Zeit vor der vollständigen
 * Panel-Schließen-/Wiedereröffnen-Funktion (Header-Bar "Ansicht hinzufügen")
 * und wurde entfernt. Dieser Test stellt sicher, dass er nicht wieder
 * auftaucht -- kein Einklapp-Button, keine Platzhalter-Darstellung.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PanelRenderer } from './PanelRenderer';
import type { PanelSelection } from '@/lib/panelHistory';

const EMPTY_SELECTION: PanelSelection = {
  selectedFile: null,
  selectedDoc: null,
  selectedEntity: null,
  selectedLine: null,
};

function renderChatPanel(overrides: Partial<React.ComponentProps<typeof PanelRenderer>> = {}) {
  return render(
    <PanelRenderer
      index={0}
      contentType="chat"
      selection={EMPTY_SELECTION}
      focusObject={null}
      theme="dark"
      t={(key: string) => key}
      selectedProject={null}
      panelFrozen={false}
      panelCount={2}
      panelHistory={{ past: [], future: [] }}
      linkManagerEnabled={false}
      content={<div>chat-content</div>}
      onContentTypeChange={vi.fn()}
      onMouseEnter={vi.fn()}
      onHistoryBack={vi.fn()}
      onHistoryForward={vi.fn()}
      onToggleFreeze={vi.fn()}
      onClose={vi.fn()}
      {...overrides}
    />
  );
}

describe('PanelRenderer', () => {
  it('renders the chat panel content directly, with no collapse/expand affordance', () => {
    renderChatPanel();

    expect(screen.getByText('chat-content')).toBeTruthy();
    expect(screen.queryByTitle('page.workspace.collapseChat')).toBeNull();
    expect(screen.queryByTitle('page.workspace.expandChat')).toBeNull();
  });

  it('does not accept a `collapsed` prop -- the chat panel can no longer be collapsed at all', () => {
    // @ts-expect-error -- `collapsed` was removed from PanelRendererProps; this
    // must not type-check, guarding against the prop silently coming back.
    renderChatPanel({ collapsed: true });

    // Even if a stray `collapsed` prop were passed through, there is no
    // branch left in the component that reacts to it -- content still shows.
    expect(screen.getByText('chat-content')).toBeTruthy();
  });

  it('still renders the close button for a non-chat panel when more than one panel is open', () => {
    renderChatPanel({ contentType: 'code', panelCount: 2 });
    expect(screen.getByTitle('page.workspace.closeView')).toBeTruthy();
  });
});
