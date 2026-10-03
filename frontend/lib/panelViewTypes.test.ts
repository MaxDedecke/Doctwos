import { describe, expect, it } from 'vitest';

import { getAvailablePanelViewTypes, PANEL_VIEW_TYPES } from './panelViewTypes';

describe('panelViewTypes', () => {
  it('offers Agentensuche and Erkenntnisse in addition to the classic views', () => {
    expect([...PANEL_VIEW_TYPES]).toEqual(
      ['chat', 'code', 'doc', 'graph', 'callgraph', 'webview', 'linkmanager', 'insights'],
    );
  });

  it('omits the Link-Manager unless it is enabled', () => {
    expect(getAvailablePanelViewTypes({ linkManagerEnabled: false })).not.toContain('linkmanager');
    expect(getAvailablePanelViewTypes({ linkManagerEnabled: true })).toContain('linkmanager');
  });

  it('keeps every other type in both modes so the menus cannot drift apart', () => {
    const without = getAvailablePanelViewTypes({ linkManagerEnabled: false });
    const withLm = getAvailablePanelViewTypes({ linkManagerEnabled: true });
    expect(withLm.filter((type) => type !== 'linkmanager')).toEqual(without);
  });
});
