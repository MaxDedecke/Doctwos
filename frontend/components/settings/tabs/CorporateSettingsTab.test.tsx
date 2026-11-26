import { createSettingsContextValue } from '@/test/settingsContext';
import { axiosResponse } from '@/test/http';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  getBranding: vi.fn(),
  saveBranding: vi.fn(),
  uploadBrandingLogo: vi.fn(),
  deleteBrandingLogo: vi.fn(),
  resetBranding: vi.fn(),
}));
vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/lib/i18n/LanguageContext', () => ({ useLanguage: () => ({ language: 'de', t: (key: string) => key }) }));
const settingsValue = createSettingsContextValue({ currentUser: { id: 1, username: 'admin', is_admin: true } });
vi.mock('@/components/settings/SettingsContext', () => ({ useSettings: () => settingsValue }));

import { DEFAULT_BRANDING, getBranding, setBranding } from '@/lib/branding';
import { CorporateSettingsTab } from './CorporateSettingsTab';

describe('CorporateSettingsTab', () => {
  afterEach(() => {
    vi.clearAllMocks();
    setBranding(null);
  });

  it('saves the form and applies the branding immediately', async () => {
    apiMocks.getBranding.mockResolvedValue(axiosResponse(DEFAULT_BRANDING));
    apiMocks.saveBranding.mockImplementation(async (data) => axiosResponse({ ...DEFAULT_BRANDING, ...data, revision: 2 }));
    render(<CorporateSettingsTab />);

    const name = await screen.findByText('settings.corporateTab.customerName');
    fireEvent.change(name.parentElement!.querySelector('input')!, { target: { value: 'Beispielkunde' } });
    fireEvent.change(screen.getByPlaceholderText('#0064d2'), { target: { value: '#7a2e8c' } });
    fireEvent.click(screen.getByText('settings.corporateTab.save'));

    await waitFor(() => expect(apiMocks.saveBranding).toHaveBeenCalled());
    expect(apiMocks.saveBranding.mock.calls[0][0]).toMatchObject({ customer_name: 'Beispielkunde', accent_color: '#7a2e8c' });
    await waitFor(() => expect(getBranding().customer_name).toBe('Beispielkunde'));
    expect(settingsValue.showToast).toHaveBeenCalledWith('settings.corporateTab.saved', 'success');
  });

  it('warns when the accent is close to a status colour', async () => {
    apiMocks.getBranding.mockResolvedValue(axiosResponse({ ...DEFAULT_BRANDING, accent_color: '#e4002b' }));
    render(<CorporateSettingsTab />);
    expect(await screen.findByText('settings.corporateTab.accentConflict.danger')).toBeTruthy();
  });

  it('uploads a logo for the chosen variant', async () => {
    apiMocks.getBranding.mockResolvedValue(axiosResponse(DEFAULT_BRANDING));
    apiMocks.uploadBrandingLogo.mockResolvedValue(axiosResponse({ ...DEFAULT_BRANDING, logo_dark_url: '/config/branding/logo/dark?r=2', revision: 2 }));
    render(<CorporateSettingsTab />);
    const input = await screen.findByTestId('branding-logo-input-dark');
    const file = new File([new Uint8Array([137, 80, 78, 71])], 'logo.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(apiMocks.uploadBrandingLogo).toHaveBeenCalledWith('dark', file));
    await waitFor(() => expect(getBranding().logo_dark_url).toBe('/config/branding/logo/dark?r=2'));
  });

  it('shows the server message when validation fails', async () => {
    apiMocks.getBranding.mockResolvedValue(axiosResponse(DEFAULT_BRANDING));
    const error = Object.assign(new Error('422'), { isAxiosError: true, response: { status: 422, data: { detail: 'Impressum: nur Adressen mit https://, http:// sind erlaubt.' } } });
    apiMocks.saveBranding.mockRejectedValue(error);
    render(<CorporateSettingsTab />);
    fireEvent.click(await screen.findByText('settings.corporateTab.save'));
    await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Impressum: nur Adressen mit https://, http:// sind erlaubt.', 'error', error));
  });
});
