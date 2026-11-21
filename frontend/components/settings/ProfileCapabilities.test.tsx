import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { api } from '@/app/services/api';
import { axiosResponse } from '@/test/http';
import type { LlmProfile } from '@/hooks/useAiSettings';
import { ProfileCapabilities } from './ProfileCapabilities';

vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({ t: (key: string) => key, language: 'de' }),
}));

const profile: LlmProfile = { id: '2', name: 'Lokal', provider: 'ollama', model: 'qwen3:8b', capabilities: null };

describe('ProfileCapabilities', () => {
  it('shows an unchecked profile and stores the result of a check', async () => {
    vi.spyOn(api, 'checkAiProfileCapabilities').mockResolvedValue(axiosResponse({
      id: 2, name: 'Lokal', provider: 'ollama', llm_model: 'qwen3:8b',
      capabilities: { tools: false, tool_arguments: false, tool_roundtrip: false, streaming: true, reasoning: true, error: null, checked_at: '2026-11-21T12:00:00Z' },
    }) as never);
    const onChecked = vi.fn();
    const showToast = vi.fn();
    const { rerender } = render(<ProfileCapabilities profile={profile} onChecked={onChecked} showToast={showToast} />);
    expect(screen.getByText('settings.profilesTab.capabilities.unchecked')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /capabilities\.check/ }));

    await waitFor(() => expect(onChecked).toHaveBeenCalled());
    const checked = onChecked.mock.calls[0][0] as LlmProfile;
    expect(checked.capabilities?.tools).toBe(false);
    expect(showToast).toHaveBeenCalledWith('settings.profilesTab.capabilities.checkedToast', 'success');
    rerender(<ProfileCapabilities profile={{ ...profile, capabilities: checked.capabilities }} onChecked={onChecked} showToast={showToast} />);
    expect(screen.getByText('settings.profilesTab.capabilities.noTools')).toBeTruthy();
    expect(screen.getByText('settings.profilesTab.capabilities.streaming')).toBeTruthy();
  });
});
