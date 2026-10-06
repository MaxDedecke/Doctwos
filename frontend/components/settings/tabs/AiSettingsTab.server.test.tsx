import { axiosResponse } from '@/test/http';
import { createSettingsContextValue } from '@/test/settingsContext';
import { DEFAULT_FEATURES, type FeaturesConfig } from '@/lib/features';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const apiMocks = vi.hoisted(() => ({
  createAiProfile: vi.fn(), updateAiProfile: vi.fn(), deleteAiProfile: vi.fn(),
  activateAiProfile: vi.fn(), testAiProfile: vi.fn(),
  getLlmDeployments: vi.fn(), createLlmDeployment: vi.fn(), controlLlmDeployment: vi.fn(), getLlmDeploymentLogs: vi.fn(),
}));
vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/lib/i18n/LanguageContext', () => ({ useLanguage: () => ({ t: (key: string) => key }) }));
let featuresValue: FeaturesConfig = DEFAULT_FEATURES;
vi.mock('@/lib/FeaturesContext', () => ({ useFeatures: () => featuresValue }));
let settingsValue = createSettingsContextValue();
vi.mock('@/components/settings/SettingsContext', () => ({ useSettings: () => settingsValue }));
import { AiSettingsTab } from './AiSettingsTab';

const local = { id: '1', name: 'Lokal', kind: 'local' as const, provider: 'ollama', protocol: 'ollama' as const, model: 'qwen3:32b', isSystem: true };
const remote = { id: '2', name: 'On-Prem', kind: 'remote' as const, provider: 'openai', protocol: 'openai_chat' as const, model: 'qwen', baseUrl: 'https://llm.local/v1' };

describe('AiSettingsTab server profiles', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    featuresValue = DEFAULT_FEATURES;
    settingsValue = createSettingsContextValue({ llmProfiles: [local, remote], activeProfileId: '1' });
    apiMocks.getLlmDeployments.mockResolvedValue(axiosResponse({ capabilities: { gpu: false }, deployments: [] }));
  });

  it('shows the three simple deployment types only when cloud is enabled', () => {
    render(<AiSettingsTab />);
    fireEvent.click(screen.getByText('settings.profilesTab.addProfile'));
    fireEvent.click(screen.getAllByRole('combobox')[0]);
    expect(within(screen.getByRole('listbox')).getByText('settings.profilesTab.local')).toBeTruthy();
    expect(within(screen.getByRole('listbox')).getByText('settings.profilesTab.remote')).toBeTruthy();
    expect(within(screen.getByRole('listbox')).queryByText('settings.profilesTab.cloud')).toBeNull();
  });

  it('creates a remote OpenAI-compatible profile on the server without putting its key in localStorage', async () => {
    apiMocks.createAiProfile.mockResolvedValue(axiosResponse({
      id: 3, name: 'GPU', kind: 'remote', provider: 'openai', protocol: 'openai_chat',
      llm_model: 'qwen', llm_base_url: 'https://gpu.local/v1', llm_path: '/chat/completions',
      llm_api_key_set: true, embedding_provider: 'ollama', embedding_model: 'qwen3-embedding:4b',
      embedding_dimension: 1024, embedding_context_length: 8192, llm_context_length: 8192,
    }));
    render(<AiSettingsTab />);
    fireEvent.click(screen.getByText('settings.profilesTab.addProfile'));
    fireEvent.click(screen.getAllByRole('combobox')[0]);
    fireEvent.click(within(screen.getByRole('listbox')).getByText('settings.profilesTab.remote'));
    fireEvent.change(screen.getByLabelText('settings.profilesTab.profileNameLabel'), { target: { value: 'GPU' } });
    const boxes = screen.getAllByRole('combobox');
    fireEvent.click(boxes[1]);
    fireEvent.click(within(screen.getByRole('listbox')).getByText('settings.profilesTab.protocolOpenai'));
    fireEvent.change(screen.getByLabelText('settings.profilesTab.modelNameLabel'), { target: { value: 'qwen' } });
    fireEvent.change(screen.getByLabelText('settings.profilesTab.apiKeyLabel'), { target: { value: 'secret' } });
    fireEvent.change(screen.getByLabelText('settings.profilesTab.baseUrlLabel'), { target: { value: 'https://gpu.local/v1' } });
    fireEvent.click(screen.getByText('settings.profilesTab.saveProfile'));
    await waitFor(() => expect(apiMocks.createAiProfile).toHaveBeenCalledWith(expect.objectContaining({ kind: 'remote', protocol: 'openai_chat', llm_api_key: 'secret' })));
    expect(localStorage.getItem('doctus-llm-profiles')).toBeNull();
  });

  it('activates a remote profile through the API', async () => {
    apiMocks.activateAiProfile.mockResolvedValue(axiosResponse({}));
    render(<AiSettingsTab />);
    fireEvent.click(screen.getByText('settings.profilesTab.activate'));
    await waitFor(() => expect(apiMocks.activateAiProfile).toHaveBeenCalledWith(2));
    expect(settingsValue.setActiveProfileId).toHaveBeenCalledWith('2');
  });

  it('tests the endpoint through the backend', async () => {
    apiMocks.testAiProfile.mockResolvedValue(axiosResponse({ ok: true }));
    render(<AiSettingsTab />);
    fireEvent.click(screen.getAllByTitle('settings.profilesTab.testProfile')[1]);
    await waitFor(() => expect(apiMocks.testAiProfile).toHaveBeenCalledWith(2));
    expect(settingsValue.showToast).toHaveBeenCalledWith('settings.profilesTab.testSuccess', 'success');
  });

  it('protects the local system profile and active profile from deletion', () => {
    render(<AiSettingsTab />);
    const trashButtons = screen.getAllByRole('button').filter(button => button.querySelector('.lucide-trash2'));
    expect(trashButtons[0].hasAttribute('disabled')).toBe(true);
  });

  describe('local deployments', () => {
    const openLocalForm = () => {
      render(<AiSettingsTab />);
      fireEvent.click(screen.getByText('settings.profilesTab.addProfile'));
    };

    it('creates a llama.cpp deployment with a container name derived from the profile name', async () => {
      apiMocks.createLlmDeployment.mockResolvedValue(axiosResponse({
        deployment: { name: 'qwen-lokal' },
        profile: { id: 9, name: 'Qwen lokal', kind: 'local', provider: 'llamacpp', protocol: 'openai_chat', llm_model: 'org/m', deployment_name: 'qwen-lokal' },
      }));
      openLocalForm();
      fireEvent.change(screen.getByLabelText('settings.profilesTab.profileNameLabel'), { target: { value: 'Qwen lokal' } });
      fireEvent.change(screen.getByLabelText('settings.profilesTab.modelNameLabel'), { target: { value: 'org/m' } });
      fireEvent.click(screen.getByText('settings.deployments.create'));
      await waitFor(() => expect(apiMocks.createLlmDeployment).toHaveBeenCalledWith(expect.objectContaining({
        name: 'qwen-lokal', display_name: 'Qwen lokal', engine: 'llamacpp', model: 'org/m', role: 'chat', gpu: false,
      })));
      await waitFor(() => expect(settingsValue.setLlmProfiles).toHaveBeenCalled());
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.deployments.created', 'success');
    });

    it('requires a GPU for vLLM and blocks creation on hosts without one', async () => {
      openLocalForm();
      fireEvent.change(screen.getByLabelText('settings.profilesTab.profileNameLabel'), { target: { value: 'Schnell' } });
      fireEvent.change(screen.getByLabelText('settings.profilesTab.modelNameLabel'), { target: { value: 'org/m' } });
      fireEvent.click(screen.getAllByRole('combobox')[1]);
      fireEvent.click(within(screen.getByRole('listbox')).getByText('vLLM'));
      expect(screen.getByText('settings.deployments.gpuRequired')).toBeTruthy();
      expect((screen.getByText('settings.deployments.create').closest('button') as HTMLButtonElement).disabled).toBe(true);
    });

    it('explains an unavailable deployer and keeps creation disabled', async () => {
      apiMocks.getLlmDeployments.mockRejectedValue({ response: { data: { detail: 'DEPLOYER_TOKEN fehlt' } } });
      openLocalForm();
      fireEvent.change(screen.getByLabelText('settings.profilesTab.profileNameLabel'), { target: { value: 'X' } });
      fireEvent.change(screen.getByLabelText('settings.profilesTab.modelNameLabel'), { target: { value: 'm' } });
      expect(await screen.findByRole('alert')).toBeTruthy();
      expect((screen.getByText('settings.deployments.create').closest('button') as HTMLButtonElement).disabled).toBe(true);
    });

    it('shows status and lets you stop a running deployment', async () => {
      settingsValue = createSettingsContextValue({
        llmProfiles: [{ ...local, id: '5', isSystem: false, deploymentName: 'qwen-lokal', provider: 'llamacpp', protocol: 'openai_chat' as const }],
        activeProfileId: '5',
      });
      apiMocks.getLlmDeployments.mockResolvedValue(axiosResponse({
        capabilities: { gpu: true },
        deployments: [{ name: 'qwen-lokal', engine: 'llamacpp', role: 'chat', model: 'm', gpu: false, status: 'ready', base_url: 'http://x' }],
      }));
      apiMocks.controlLlmDeployment.mockResolvedValue(axiosResponse({}));
      render(<AiSettingsTab />);
      expect(await screen.findByText('settings.deployments.status.ready')).toBeTruthy();
      fireEvent.click(screen.getByTitle('settings.deployments.stop'));
      await waitFor(() => expect(apiMocks.controlLlmDeployment).toHaveBeenCalledWith('qwen-lokal', 'stop'));
    });

    it('shows the container log on demand', async () => {
      settingsValue = createSettingsContextValue({
        llmProfiles: [{ ...local, id: '5', isSystem: false, deploymentName: 'qwen-lokal' }], activeProfileId: '5',
      });
      apiMocks.getLlmDeployments.mockResolvedValue(axiosResponse({
        capabilities: { gpu: false },
        deployments: [{ name: 'qwen-lokal', engine: 'ollama', role: 'chat', model: 'm', gpu: false, status: 'starting', base_url: 'http://x' }],
      }));
      apiMocks.getLlmDeploymentLogs.mockResolvedValue(axiosResponse({ logs: 'loading model' }));
      render(<AiSettingsTab />);
      fireEvent.click(await screen.findByTitle('settings.deployments.logs'));
      expect((await screen.findByTestId('deployment-logs')).textContent).toBe('loading model');
    });
  });
});
