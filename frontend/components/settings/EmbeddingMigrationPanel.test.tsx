import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const { apiMocks } = vi.hoisted(() => ({
  apiMocks: {
    getEmbeddingMigration: vi.fn(),
    getEmbeddingProfiles: vi.fn().mockResolvedValue({ data: { profiles: [
      { id: 1, name: 'Lokal', model: 'bge-m3' },
      { id: 2, name: 'Neu', model: 'qwen3-embedding' },
    ] } }),
    startEmbeddingMigration: vi.fn().mockResolvedValue({ data: {} }),
    embeddingMigrationAction: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

vi.mock('@/app/services/api', () => ({ api: apiMocks }));
vi.mock('@/components/settings/SettingsContext', () => ({ useSettings: () => ({ theme: 'light', showToast: vi.fn() }) }));
vi.mock('@/lib/i18n/LanguageContext', () => ({ useLanguage: () => ({ t: (key: string) => key }) }));

import { EmbeddingMigrationPanel } from './EmbeddingMigrationPanel';

const base = { models: { 'bge-m3': 120 }, without_embedding: 0, project_profile: { id: 1, name: 'Lokal', model: 'bge-m3' } };

afterEach(() => vi.clearAllMocks());

describe('EmbeddingMigrationPanel', () => {
  it('offers only other models as target and starts the change for the chosen profile', async () => {
    apiMocks.getEmbeddingMigration.mockResolvedValue({ data: { ...base, migration: null } });
    render(<EmbeddingMigrationPanel projectId={5} isAdmin />);

    const select = await screen.findByLabelText('settings.projects.embedding.target');
    expect(screen.queryByRole('option', { name: 'Lokal (bge-m3)' })).toBeNull();
    fireEvent.change(select, { target: { value: '2' } });
    fireEvent.click(screen.getByText('settings.projects.embedding.start'));

    await waitFor(() => expect(apiMocks.startEmbeddingMigration).toHaveBeenCalledWith(5, 2));
  });

  it('switches a ready change and offers rollback only after switching', async () => {
    apiMocks.getEmbeddingMigration.mockResolvedValue({ data: { ...base, migration: {
      id: 9, status: 'ready', target_model: 'qwen3-embedding', previous_model: 'bge-m3', total: 120, done: 120,
    } } });
    render(<EmbeddingMigrationPanel projectId={5} isAdmin />);

    fireEvent.click(await screen.findByText('settings.projects.embedding.switch'));
    await waitFor(() => expect(apiMocks.embeddingMigrationAction).toHaveBeenCalledWith(5, 9, 'switch'));
    expect(screen.queryByText('settings.projects.embedding.rollback')).toBeNull();
  });

  it('shows the state but no actions to project members', async () => {
    apiMocks.getEmbeddingMigration.mockResolvedValue({ data: { ...base, migration: null } });
    render(<EmbeddingMigrationPanel projectId={5} isAdmin={false} />);

    expect(await screen.findByText('settings.projects.embedding.title')).toBeInTheDocument();
    expect(screen.queryByText('settings.projects.embedding.start')).toBeNull();
  });
});
