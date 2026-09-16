import type { LlmProfile } from '@/hooks/useAiSettings';
import { axiosResponse } from '@/test/http';
import { createSettingsContextValue } from '@/test/settingsContext';
import { DEFAULT_FEATURES, type FeaturesConfig } from '@/lib/features';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const apiMocks = vi.hoisted(() => ({ updateAiSettings: vi.fn() }));

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/lib/i18n/LanguageContext', () => ({ useLanguage: () => ({ t: (key: string) => key }) }));

let featuresValue: FeaturesConfig = DEFAULT_FEATURES;
vi.mock('@/lib/FeaturesContext', () => ({ useFeatures: () => featuresValue }));

let settingsValue = createSettingsContextValue();
vi.mock('@/components/settings/SettingsContext', () => ({
  useSettings: () => settingsValue,
}));

import { AiSettingsTab } from './AiSettingsTab';

const profile = (overrides: Partial<LlmProfile> = {}): LlmProfile => ({
  id: 'p1', name: 'Lokal', provider: 'ollama', model: 'qwen3:32b', ...overrides,
});

/** Findet die Select-Trigger-Combobox, die zu diesem Label-Text gehört. */
function comboboxForLabel(labelText: string): HTMLElement {
  return within(screen.getByText(labelText).closest('div')!).getByRole('combobox');
}

describe('AiSettingsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    settingsValue = createSettingsContextValue({
      llmProfiles: [profile()],
      activeProfileId: 'p1',
    });
    featuresValue = DEFAULT_FEATURES;
  });

  afterEach(() => {
    localStorage.clear();
  });

  describe('Profilauswahl', () => {
    it('marks the active profile and lets you switch to another one', () => {
      settingsValue = createSettingsContextValue({
        llmProfiles: [profile({ id: 'p1', name: 'Lokal' }), profile({ id: 'p2', name: 'Cloud', provider: 'openai', model: 'gpt-4o' })],
        activeProfileId: 'p1',
      });
      render(<AiSettingsTab />);

      expect(screen.getByText('settings.profilesTab.active')).toBeTruthy();

      fireEvent.click(comboboxForLabel('settings.profilesTab.activeProfileLabel'));
      fireEvent.click(within(screen.getByRole('listbox')).getByText('Cloud (gpt-4o)'));

      expect(settingsValue.setActiveProfileId).toHaveBeenCalledWith('p2');
    });
  });

  describe('Profil hinzufügen', () => {
    it('prefills the form with the Ollama defaults', () => {
      render(<AiSettingsTab />);
      fireEvent.click(screen.getByText('settings.profilesTab.addProfile'));

      expect((screen.getByPlaceholderText('settings.profilesTab.profileNamePlaceholder') as HTMLInputElement).value).toBe('');
      expect(screen.getByDisplayValue('qwen3:32b')).toBeTruthy();
    });

    it('requires a name before saving', () => {
      render(<AiSettingsTab />);
      fireEvent.click(screen.getByText('settings.profilesTab.addProfile'));
      fireEvent.click(screen.getByText('settings.profilesTab.saveProfile'));

      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.profileNameRequired', 'error');
      expect(settingsValue.setLlmProfiles).not.toHaveBeenCalled();
    });

    it('requires a model name before saving', () => {
      render(<AiSettingsTab />);
      fireEvent.click(screen.getByText('settings.profilesTab.addProfile'));
      fireEvent.change(screen.getByPlaceholderText('settings.profilesTab.profileNamePlaceholder'), { target: { value: 'Neu' } });
      fireEvent.change(screen.getByDisplayValue('qwen3:32b'), { target: { value: '' } });
      fireEvent.click(screen.getByText('settings.profilesTab.saveProfile'));

      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.modelNameRequired', 'error');
      expect(settingsValue.setLlmProfiles).not.toHaveBeenCalled();
    });

    it('adds the new profile, persists it, and closes the form', () => {
      render(<AiSettingsTab />);
      fireEvent.click(screen.getByText('settings.profilesTab.addProfile'));
      fireEvent.change(screen.getByPlaceholderText('settings.profilesTab.profileNamePlaceholder'), { target: { value: 'Neu' } });
      fireEvent.change(screen.getByPlaceholderText('settings.profilesTab.apiKeyPlaceholder'), { target: { value: 'secret' } });
      fireEvent.click(screen.getByText('settings.profilesTab.saveProfile'));

      expect(settingsValue.setLlmProfiles).toHaveBeenCalledWith([
        profile(),
        expect.objectContaining({ name: 'Neu', provider: 'ollama', model: 'qwen3:32b', apiKey: 'secret' }),
      ]);
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.profileCreated', 'success');
      const stored = JSON.parse(localStorage.getItem('doctus-llm-profiles')!);
      expect(stored).toHaveLength(2);
      expect(screen.queryByText('settings.profilesTab.saveProfile')).toBeNull();
    });

    it('changing the provider swaps the model to that provider\'s default (Modellwechsel)', () => {
      featuresValue = { ...DEFAULT_FEATURES, llm: { allowCloudProviders: true } };
      render(<AiSettingsTab />);
      fireEvent.click(screen.getByText('settings.profilesTab.addProfile'));
      expect(screen.getByDisplayValue('qwen3:32b')).toBeTruthy();

      fireEvent.click(comboboxForLabel('settings.profilesTab.providerLabel'));
      fireEvent.click(within(screen.getByRole('listbox')).getByText('settings.profilesTab.providerOptions.openai'));

      expect(screen.getByDisplayValue('gpt-4o')).toBeTruthy();
    });

    it('does not override a manually entered model when switching providers', () => {
      featuresValue = { ...DEFAULT_FEATURES, llm: { allowCloudProviders: true } };
      render(<AiSettingsTab />);
      fireEvent.click(screen.getByText('settings.profilesTab.addProfile'));
      fireEvent.change(screen.getByDisplayValue('qwen3:32b'), { target: { value: 'my-custom-model' } });

      fireEvent.click(comboboxForLabel('settings.profilesTab.providerLabel'));
      fireEvent.click(within(screen.getByRole('listbox')).getByText('settings.profilesTab.providerOptions.openai'));

      expect(screen.getByDisplayValue('my-custom-model')).toBeTruthy();
    });

    it('hides cloud providers when they are not allowed (on-prem default)', () => {
      render(<AiSettingsTab />);
      fireEvent.click(screen.getByText('settings.profilesTab.addProfile'));
      fireEvent.click(comboboxForLabel('settings.profilesTab.providerLabel'));

      const listbox = screen.getByRole('listbox');
      expect(within(listbox).getByText('settings.profilesTab.providerOptions.ollama')).toBeTruthy();
      expect(within(listbox).queryByText('settings.profilesTab.providerOptions.openai')).toBeNull();
    });
  });

  describe('Profil bearbeiten', () => {
    it('prefills the form with the existing profile and updates it in place on save', () => {
      settingsValue = createSettingsContextValue({
        llmProfiles: [profile({ id: 'p1', name: 'Lokal' }), profile({ id: 'p2', name: 'Cloud', provider: 'openai', model: 'gpt-4o' })],
        activeProfileId: 'p1',
      });
      render(<AiSettingsTab />);
      fireEvent.click(screen.getAllByTitle('settings.profilesTab.editProfileTitle')[1]);

      expect((screen.getByPlaceholderText('settings.profilesTab.profileNamePlaceholder') as HTMLInputElement).value).toBe('Cloud');
      fireEvent.change(screen.getByDisplayValue('Cloud'), { target: { value: 'Cloud v2' } });
      fireEvent.click(screen.getByText('settings.profilesTab.saveProfile'));

      expect(settingsValue.setLlmProfiles).toHaveBeenCalledWith([
        profile({ id: 'p1', name: 'Lokal' }),
        expect.objectContaining({ id: 'p2', name: 'Cloud v2', provider: 'openai', model: 'gpt-4o' }),
      ]);
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.profileUpdated', 'success');
    });
  });

  describe('Profil löschen', () => {
    it('disables deletion when only one profile remains', () => {
      render(<AiSettingsTab />);
      expect(screen.getByTitle('settings.profilesTab.deleteProfileTitle').hasAttribute('disabled')).toBe(true);
    });

    it('deletes exactly the targeted, non-active profile without changing the active one', () => {
      settingsValue = createSettingsContextValue({
        llmProfiles: [profile({ id: 'p1', name: 'Lokal' }), profile({ id: 'p2', name: 'Cloud' })],
        activeProfileId: 'p1',
      });
      render(<AiSettingsTab />);
      fireEvent.click(screen.getAllByTitle('settings.profilesTab.deleteProfileTitle')[1]);

      expect(settingsValue.setLlmProfiles).toHaveBeenCalledWith([profile({ id: 'p1', name: 'Lokal' })]);
      expect(settingsValue.setActiveProfileId).not.toHaveBeenCalled();
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.profileDeleted', 'success');
    });

    it('reassigns the active profile to the first remaining one when the active profile is deleted', () => {
      settingsValue = createSettingsContextValue({
        llmProfiles: [profile({ id: 'p1', name: 'Lokal' }), profile({ id: 'p2', name: 'Cloud' })],
        activeProfileId: 'p2',
      });
      render(<AiSettingsTab />);
      fireEvent.click(screen.getAllByTitle('settings.profilesTab.deleteProfileTitle')[1]);

      expect(settingsValue.setActiveProfileId).toHaveBeenCalledWith('p1');
    });
  });

  describe('KI-Parameter speichern', () => {
    it('updates the temperature display and forwards the raw value', () => {
      render(<AiSettingsTab />);
      fireEvent.change(screen.getByRole('slider'), { target: { value: '0.3' } });
      expect(settingsValue.setTemperature).toHaveBeenCalledWith(0.3);
    });

    it('sends the correct model for the active Ollama profile and persists temperature/prompt into it', async () => {
      apiMocks.updateAiSettings.mockResolvedValue(axiosResponse({}));
      settingsValue = createSettingsContextValue({
        llmProfiles: [profile({ id: 'p1', model: 'llama3' })],
        activeProfileId: 'p1',
        temperature: 0.5,
        systemPrompt: 'Sei präzise.',
      });
      render(<AiSettingsTab />);
      fireEvent.click(screen.getByText('settings.profilesTab.saveAiSettings'));

      await waitFor(() => expect(apiMocks.updateAiSettings).toHaveBeenCalledWith(expect.objectContaining({ llm_model: 'llama3' })));
      expect(settingsValue.setLlmProfiles).toHaveBeenCalledWith([
        expect.objectContaining({ id: 'p1', temperature: 0.5, systemPrompt: 'Sei präzise.' }),
      ]);
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.aiParamsSaved', 'success');
    });

    it('does not call the model-info endpoint for a non-Ollama (cloud) profile', async () => {
      settingsValue = createSettingsContextValue({
        llmProfiles: [profile({ id: 'p1', provider: 'openai', model: 'gpt-4o' })],
        activeProfileId: 'p1',
      });
      render(<AiSettingsTab />);
      fireEvent.click(screen.getByText('settings.profilesTab.saveAiSettings'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.aiParamsSaved', 'success'));
      expect(apiMocks.updateAiSettings).toHaveBeenCalled();
    });

    it('shows a failure toast when the local LLM is unreachable', async () => {
      apiMocks.updateAiSettings.mockRejectedValue(new Error('ECONNREFUSED'));
      render(<AiSettingsTab />);
      fireEvent.click(screen.getByText('settings.profilesTab.saveAiSettings'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.aiParamsSaveFailed', 'error', expect.any(Error)));
    });
  });
});
