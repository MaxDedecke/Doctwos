import { axiosResponse } from '@/test/http';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { GraphSourceFocus } from './GraphSourceFocus';

const apiMocks = vi.hoisted(() => ({ getKnowledgeSources: vi.fn() }));
vi.mock('@/app/services/api', () => ({ api: apiMocks }));
vi.mock('@/lib/i18n/LanguageContext', () => ({ useLanguage: () => ({ t: (key: string) => key }) }));

const source = (id: number, name: string, project_id: number) => ({ id, name, project_id });

describe('GraphSourceFocus', () => {
  it('bietet nur Quellen des Projekts an und meldet die gewählte Quelle', async () => {
    apiMocks.getKnowledgeSources.mockResolvedValue(
      axiosResponse([source(8, 'git', 2), source(968, 'jira', 2), source(7, 'andere', 1)]),
    );
    const onChange = vi.fn();
    render(<GraphSourceFocus isDark projectId={2} value={null} onChange={onChange} />);

    const select = await screen.findByRole('combobox');
    expect(screen.queryByText('andere')).toBeNull();
    fireEvent.change(select, { target: { value: '968' } });
    expect(onChange).toHaveBeenCalledWith(968);
    fireEvent.change(select, { target: { value: '' } });
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it('blendet sich bei weniger als zwei Quellen aus', async () => {
    apiMocks.getKnowledgeSources.mockResolvedValue(axiosResponse([source(8, 'git', 2)]));
    render(<GraphSourceFocus isDark={false} projectId={2} value={null} onChange={vi.fn()} />);

    await waitFor(() => expect(apiMocks.getKnowledgeSources).toHaveBeenCalled());
    expect(screen.queryByRole('combobox')).toBeNull();
  });
});
