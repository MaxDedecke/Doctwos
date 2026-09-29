import { DEFAULT_FEATURES } from '@/lib/features';
import { createSettingsContextValue } from '@/test/settingsContext';
import { axiosResponse } from '@/test/http';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  getMcpTokens: vi.fn(),
  getMcpToolAuditLogs: vi.fn(),
  getSystemConfig: vi.fn(),
}));
vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({ language: 'de', t: (key: string, values?: Record<string, string | number>) => (values ? `${key}:${Object.values(values).join('/')}` : key) }),
}));
vi.mock('@/lib/FeaturesContext', () => ({ useFeatures: () => DEFAULT_FEATURES }));
let settingsValue = createSettingsContextValue();
vi.mock('@/components/settings/SettingsContext', () => ({ useSettings: () => settingsValue }));

import { AiSettingsTab } from './AiSettingsTab';
import { ConfigSettingsTab } from './ConfigSettingsTab';
import { McpSettingsTab } from './McpSettingsTab';

const config = {
  sso: { enabled: true, issuer: 'https://idp.test', client_id: 'doctus', client_secret_configured: true, redirect_uri: null, default_team: null, default_team_exists: null, admin_roles: [], team_mapping: {}, roles_claim: 'roles', groups_claim: 'groups' },
  system: { version: '1', api_url: 'a', frontend_url: 'f', log_level: 'INFO', mcp_audit_retention_days: 90, watched_folder: null },
  existing_teams: [],
};

/**
 * Die Tabs IDE / MCP, AI-Parameter und System & SSO sollen dieselbe Gestaltung
 * verwenden wie Projekte, Wissensquellen, Teams usw. (docs/DESIGN_GUIDELINES.md,
 * gemeinsame Bausteine in components/settings/settingsStyles.ts).
 */
function expectSharedDesign(container: HTMLElement, theme: 'dark' | 'light') {
  const html = container.innerHTML;
  // Radius: Standard 6 px (rounded-lg), keine größeren Karten (rounded-xl).
  expect(html).not.toContain('rounded-xl');
  // Wurzelcontainer und Abschnittsüberschriften wie in den übrigen Tabs.
  expect(container.firstElementChild?.className).toContain('space-y-6');
  expect(container.firstElementChild?.className).toContain('animate-in');
  expect(html).toContain('text-xs font-bold uppercase tracking-wide');
  // Themenabhängige Flächen statt fester Farben.
  expect(html).toContain(theme === 'dark' ? 'bg-ds-zinc-950/20' : 'bg-ds-zinc-50');
  // `text-white` erzeugt im Theme kein CSS; Buttons nutzen text-ds-white.
  expect(html).not.toMatch(/(^|[\s"])text-white([\s"]|$)/);
}

describe.each(['dark', 'light'] as const)('shared tab design (%s)', (theme) => {
  const setup = () => {
    settingsValue = createSettingsContextValue({ theme, currentUser: { id: 1, username: 'admin', is_admin: true }, llmProfiles: [{ id: '1', name: 'Lokal', kind: 'local', provider: 'ollama', protocol: 'ollama', model: 'qwen3:32b', isSystem: true }, { id: '2', name: 'On-Prem', kind: 'remote', provider: 'openai', protocol: 'openai_chat', model: 'qwen', baseUrl: 'https://llm.local/v1' }], activeProfileId: '1' });
    apiMocks.getMcpTokens.mockResolvedValue(axiosResponse([{ id: 1, name: 'Meine IDE', prefix: 'dct_mcp_ab', created_at: '2026-09-01T00:00:00Z', expires_at: '2099-01-01T00:00:00Z', revoked_at: null }]));
    apiMocks.getMcpToolAuditLogs.mockResolvedValue(axiosResponse({ entries: [], total: 0, offset: 0, limit: 20, retention_days: 30 }));
    apiMocks.getSystemConfig.mockResolvedValue(axiosResponse(config));
  };

  it('IDE / MCP', async () => {
    setup();
    const { container } = render(<McpSettingsTab />);
    await screen.findByText('Meine IDE');
    expectSharedDesign(container, theme);
  });

  it('AI-Parameter', () => {
    setup();
    const { container } = render(<AiSettingsTab />);
    expectSharedDesign(container, theme);
  });

  it('System & SSO', async () => {
    setup();
    const { container } = render(<ConfigSettingsTab />);
    await waitFor(() => expect(screen.getByText('System- & Laufzeit-Konfiguration')).toBeTruthy());
    expectSharedDesign(container, theme);
  });
});
