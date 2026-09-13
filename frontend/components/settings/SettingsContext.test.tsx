import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import React from 'react';

import { SettingsProvider, useSettings } from './SettingsContext';
import { createSettingsContextValue } from '@/test/settingsContext';

// SettingsContext selbst hatte trotz O-102 (der von ihm abhängigen Test-Hilfsfunktion)
// noch keinen eigenen Test: die Fehlermeldung außerhalb eines Providers ist der einzige
// Programmzweig in dieser Datei, der Fachlogik enthält (kein reines Passthrough).

function Consumer() {
  const { connectedSources, currentUser } = useSettings();
  return <span>{connectedSources.length} Quellen, Nutzer: {currentUser?.username}</span>;
}

describe('useSettings', () => {
  it('throws when used outside a SettingsProvider', () => {
    // React loggt den Fehler zusätzlich auf die Konsole; das ist hier nicht Gegenstand des Tests.
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Consumer />)).toThrow('useSettings must be used within a SettingsProvider');
    consoleSpy.mockRestore();
  });

  it('returns the provided value inside a SettingsProvider', () => {
    const value = createSettingsContextValue({
      connectedSources: [{ id: 1, name: 'X' }, { id: 2, name: 'Y' }],
      currentUser: { id: 7, username: 'maxi', is_admin: false },
    });
    render(
      <SettingsProvider value={value}>
        <Consumer />
      </SettingsProvider>
    );
    expect(screen.getByText('2 Quellen, Nutzer: maxi')).toBeTruthy();
  });
});
