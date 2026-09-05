/**
 * SSO-Ergänzung der Login-Seite (E-12/O-041): der Button erscheint nur, wenn
 * das Deployment SSO konfiguriert hat (core/config.py::oidc_enabled(), über
 * GET /config/features -> lib/features.ts durchgereicht), leitet zum
 * Backend-OIDC-Login weiter, und ein Fehler aus GET /auth/oidc/callback
 * (Query-Param `oidc_error`, siehe backend/api/auth.py::_oidc_error_redirect)
 * wird einmalig angezeigt und danach aus der URL entfernt.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LoginView } from './LoginView';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import * as featuresModule from '@/lib/features';

function renderLoginView() {
  return render(
    <LanguageProvider>
      <LoginView />
    </LanguageProvider>
  );
}

describe('LoginView SSO button', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState({}, '', '/');
  });

  it('is hidden when this deployment has no SSO configured', () => {
    vi.spyOn(featuresModule, 'getFeatures').mockReturnValue({
      ...featuresModule.DEFAULT_FEATURES,
      auth: { ssoEnabled: false },
    });

    renderLoginView();

    expect(screen.queryByText('Mit Single Sign-On anmelden')).toBeNull();
  });

  it('appears when this deployment has SSO configured', () => {
    vi.spyOn(featuresModule, 'getFeatures').mockReturnValue({
      ...featuresModule.DEFAULT_FEATURES,
      auth: { ssoEnabled: true },
    });

    renderLoginView();

    expect(screen.getByText('Mit Single Sign-On anmelden')).toBeTruthy();
  });

  describe('clicking the SSO button', () => {
    const originalLocation = window.location;

    afterEach(() => {
      // @ts-expect-error -- jsdom's window.location can only be reassigned
      // after deleting it first; restored to the real object afterwards so
      // other tests in this file keep a working location.
      delete window.location;
      window.location = originalLocation;
    });

    it('navigates the browser to the backend OIDC login endpoint', () => {
      // @ts-expect-error -- see above
      delete window.location;
      window.location = { ...originalLocation, href: '' } as Location;
      vi.spyOn(featuresModule, 'getFeatures').mockReturnValue({
        ...featuresModule.DEFAULT_FEATURES,
        auth: { ssoEnabled: true },
      });

      renderLoginView();
      fireEvent.click(screen.getByText('Mit Single Sign-On anmelden'));

      expect(window.location.href).toBe('http://localhost:8000/auth/oidc/login');
    });
  });

  it('shows an error redirected back from a failed SSO callback and removes it from the URL', async () => {
    window.history.replaceState({}, '', '/?oidc_error=Sitzung%20abgelaufen');
    vi.spyOn(featuresModule, 'getFeatures').mockReturnValue(featuresModule.DEFAULT_FEATURES);

    renderLoginView();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Sitzung abgelaufen');
    // Ein Neuladen der Seite darf denselben Fehler nicht noch einmal zeigen.
    expect(window.location.search).toBe('');
  });

  it('does not show an error when no oidc_error query param is present', () => {
    vi.spyOn(featuresModule, 'getFeatures').mockReturnValue(featuresModule.DEFAULT_FEATURES);

    renderLoginView();

    expect(screen.queryByRole('alert')).toBeNull();
  });
});
