import { axiosResponse } from '@/test/http';
/**
 * O-059: `JobCenter.tsx` hatte keinen Test -- Job-Liste, die vier Aktionen
 * (Wiederaufnehmen/Neu anstoßen/Stoppen/Entfernen) und vor allem das
 * Rollen-Gating waren ungeprüft. Das Gating ist dabei nicht nur ein
 * "Admin sieht mehr": `Wiederaufnehmen` erscheint ausschließlich für
 * Nicht-Admins, während Admins stattdessen `Neu anstoßen` und `Stoppen`
 * bekommen -- genau die Art Regel, die beim Umbauen unbemerkt kippt.
 *
 * Das Panel pollt alle 3 Sekunden per `setInterval`. Die Tests warten nur auf
 * den ersten Abruf und prüfen Nachlade-Verhalten über die Aktionen, statt die
 * Uhr vorzustellen -- so bleibt jeder Fall unabhängig vom Poll-Takt.
 */
import { api } from '@/app/services/api';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { JobCenter } from './JobCenter';

vi.mock('@/app/services/api', () => ({
  api: {
    getJobs: vi.fn(),
    resumeJob: vi.fn(),
    startJob: vi.fn(),
    stopJob: vi.fn(),
    deleteJob: vi.fn(),
  },
}));

type Job = {
  key: string; kind: string; id: number; label: string; status: string;
  progress: number | null; progress_message?: string; error_message?: string;
  can_resume: boolean; can_start?: boolean; can_delete?: boolean; can_stop?: boolean;
};

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    key: 'git:1',
    kind: 'git',
    id: 1,
    label: 'COBOL-Repo synchronisieren',
    status: 'running',
    progress: null,
    can_resume: false,
    ...overrides,
  };
}

function stubJobs(jobs: Job[], activeCount = 0) {
  vi.mocked(api.getJobs).mockResolvedValue(axiosResponse({ jobs, active_count: activeCount }));
}

const ADMIN = { is_admin: true };
const USER = { is_admin: false };

function renderJobCenter(props: Partial<React.ComponentProps<typeof JobCenter>> = {}) {
  return render(
    <LanguageProvider>
      <JobCenter theme="dark" currentUser={USER} {...(props)} />
    </LanguageProvider>
  );
}

/** Öffnet das Panel und wartet, bis die erste Job-Liste da ist. */
async function openPanel(props: Partial<React.ComponentProps<typeof JobCenter>> = {}) {
  const view = renderJobCenter(props);
  await waitFor(() => expect(api.getJobs).toHaveBeenCalled());
  fireEvent.click(screen.getByLabelText('Job-Center'));
  return view;
}

/** Ein abgelehnter axios-Aufruf, so wie die Komponente ihn auswertet. */
function apiError(detail?: string) {
  return Object.assign(new Error('request failed'), { isAxiosError: true, response: { status: 400, data: detail ? { detail } : {} } });
}

describe('JobCenter', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  describe('Job-Liste', () => {
    it('bleibt geschlossen, bis der Knopf gedrückt wird', async () => {
      stubJobs([makeJob()]);

      renderJobCenter();
      await waitFor(() => expect(api.getJobs).toHaveBeenCalled());

      expect(screen.queryByRole('heading', { name: 'Job-Center' })).toBeNull();

      fireEvent.click(screen.getByLabelText('Job-Center'));
      expect(screen.getByRole('heading', { name: 'Job-Center' })).toBeTruthy();
    });

    it('zeigt Label und übersetzten Status eines Jobs', async () => {
      stubJobs([makeJob({ status: 'syncing', progress_message: 'Datei 12 von 40' })]);

      await openPanel();

      expect(await screen.findByText('COBOL-Repo synchronisieren')).toBeTruthy();
      expect(screen.getByText('Synchronisierung')).toBeTruthy();
      expect(screen.getByText('Datei 12 von 40')).toBeTruthy();
    });

    it('meldet eine leere Liste als solche', async () => {
      stubJobs([]);

      await openPanel();

      expect(await screen.findByText('Noch keine Jobs vorhanden.')).toBeTruthy();
    });

    it('zeigt die Zahl der aktiven Jobs am Knopf, sonst nichts', async () => {
      stubJobs([makeJob()], 3);

      const { unmount } = renderJobCenter();
      await waitFor(() => expect(screen.getByText('3')).toBeTruthy());
      unmount();

      vi.mocked(api.getJobs).mockClear();
      stubJobs([makeJob({ status: 'completed' })], 0);
      renderJobCenter();
      await waitFor(() => expect(api.getJobs).toHaveBeenCalled());
      expect(screen.queryByText('0')).toBeNull();
    });

    it('zeigt einen Fortschrittsbalken nur für laufende Jobs mit Fortschritt', async () => {
      stubJobs([
        makeJob({ key: 'git:1', id: 1, status: 'running', progress: 40 }),
        makeJob({ key: 'git:2', id: 2, label: 'Fertiger Job', status: 'completed', progress: 100 }),
        makeJob({ key: 'git:3', id: 3, label: 'Job ohne Fortschritt', status: 'running', progress: null }),
      ]);

      const { container } = await openPanel();
      await screen.findByText('COBOL-Repo synchronisieren');

      const bars = container.querySelectorAll<HTMLElement>('.bg-ds-indigo-500');
      expect(bars).toHaveLength(1);
      expect(bars[0].style.width).toBe('40%');
    });

    it('klappt die Fehlermeldung eines fehlgeschlagenen Jobs auf und wieder zu', async () => {
      stubJobs([makeJob({ status: 'failed', error_message: 'fatal: repository not found' })]);

      await openPanel();
      await screen.findByText('Fehlgeschlagen');

      const toggle = screen.getByRole('button', { expanded: false });
      fireEvent.click(toggle);
      expect(screen.getByText('fatal: repository not found')).toBeTruthy();

      // Erneut derselbe Knopf -- nach dem Aufklappen traegt auch der
      // Panel-Knopf aria-expanded="true", eine Rollen-Suche waere mehrdeutig.
      fireEvent.click(toggle);
      expect(screen.queryByText('fatal: repository not found')).toBeNull();
    });

    it('bietet keinen Aufklapper, wenn ein fehlgeschlagener Job keine Meldung mitliefert', async () => {
      stubJobs([makeJob({ status: 'failed' })]);

      await openPanel();
      await screen.findByText('Fehlgeschlagen');

      expect(screen.queryByRole('button', { expanded: false })).toBeNull();
    });

    it('fragt die Jobs des gewählten Projekts ab', async () => {
      stubJobs([]);

      renderJobCenter({ projectId: 7 });

      await waitFor(() => expect(api.getJobs).toHaveBeenCalledWith(7));
    });

    it('schließt das Panel bei einem Klick daneben', async () => {
      stubJobs([makeJob()]);

      await openPanel();
      expect(screen.getByRole('heading', { name: 'Job-Center' })).toBeTruthy();

      fireEvent.mouseDown(document.body);

      expect(screen.queryByRole('heading', { name: 'Job-Center' })).toBeNull();
    });
  });

  describe('Rollen-Gating', () => {
    const resumable = makeJob({ status: 'failed', can_resume: true, can_start: true, can_stop: true, can_delete: true });

    it('zeigt einem Nicht-Admin nur das Wiederaufnehmen', async () => {
      stubJobs([resumable]);

      await openPanel({ currentUser: USER });
      await screen.findByText('COBOL-Repo synchronisieren');

      expect(screen.getByText('Wiederaufnehmen')).toBeTruthy();
      expect(screen.queryByText('Neu anstoßen')).toBeNull();
      expect(screen.queryByText('Stoppen')).toBeNull();
      expect(screen.queryByLabelText('Aus dem Job-Center entfernen')).toBeNull();
    });

    it('zeigt einem Admin Neu anstoßen, Stoppen und Entfernen -- aber kein Wiederaufnehmen', async () => {
      stubJobs([resumable]);

      await openPanel({ currentUser: ADMIN });
      await screen.findByText('COBOL-Repo synchronisieren');

      expect(screen.getByText('Neu anstoßen')).toBeTruthy();
      expect(screen.getByText('Stoppen')).toBeTruthy();
      expect(screen.getByLabelText('Aus dem Job-Center entfernen')).toBeTruthy();
      expect(screen.queryByText('Wiederaufnehmen')).toBeNull();
    });

    it('behandelt einen fehlenden Nutzer wie einen Nicht-Admin', async () => {
      stubJobs([resumable]);

      await openPanel({ currentUser: null });
      await screen.findByText('COBOL-Repo synchronisieren');

      expect(screen.getByText('Wiederaufnehmen')).toBeTruthy();
      expect(screen.queryByText('Stoppen')).toBeNull();
    });

    it('richtet sich auch beim Admin nach den can_-Flags des Jobs', async () => {
      stubJobs([makeJob({ status: 'completed', can_resume: false, can_start: false, can_stop: false, can_delete: false })]);

      await openPanel({ currentUser: ADMIN });
      await screen.findByText('COBOL-Repo synchronisieren');

      expect(screen.queryByText('Neu anstoßen')).toBeNull();
      expect(screen.queryByText('Stoppen')).toBeNull();
      expect(screen.queryByLabelText('Aus dem Job-Center entfernen')).toBeNull();
    });
  });

  describe('Aktionen', () => {
    it('nimmt einen Job wieder auf und lädt danach neu', async () => {
      stubJobs([makeJob({ status: 'failed', can_resume: true })]);
      vi.mocked(api.resumeJob).mockResolvedValue(axiosResponse({}));

      await openPanel({ currentUser: USER });
      const before = vi.mocked(api.getJobs).mock.calls.length;

      fireEvent.click(await screen.findByText('Wiederaufnehmen'));

      await waitFor(() => expect(api.resumeJob).toHaveBeenCalledWith('git', 1));
      await waitFor(() => expect(vi.mocked(api.getJobs).mock.calls.length).toBeGreaterThan(before));
    });

    it('stößt einen Job als Admin neu an und lädt danach neu', async () => {
      stubJobs([makeJob({ status: 'failed', can_start: true })]);
      vi.mocked(api.startJob).mockResolvedValue(axiosResponse({}));

      await openPanel({ currentUser: ADMIN });
      const before = vi.mocked(api.getJobs).mock.calls.length;

      fireEvent.click(await screen.findByText('Neu anstoßen'));

      await waitFor(() => expect(api.startJob).toHaveBeenCalledWith('git', 1));
      await waitFor(() => expect(vi.mocked(api.getJobs).mock.calls.length).toBeGreaterThan(before));
    });

    it('stoppt einen laufenden Job als Admin und lädt danach neu', async () => {
      stubJobs([makeJob({ status: 'running', can_stop: true })]);
      vi.mocked(api.stopJob).mockResolvedValue(axiosResponse({}));

      await openPanel({ currentUser: ADMIN });
      const before = vi.mocked(api.getJobs).mock.calls.length;

      fireEvent.click(await screen.findByText('Stoppen'));

      await waitFor(() => expect(api.stopJob).toHaveBeenCalledWith('git', 1));
      await waitFor(() => expect(vi.mocked(api.getJobs).mock.calls.length).toBeGreaterThan(before));
    });

    it('entfernt einen Job aus der Liste, ohne dafür neu zu laden', async () => {
      stubJobs([makeJob({ status: 'completed', can_delete: true })]);
      vi.mocked(api.deleteJob).mockResolvedValue(axiosResponse({}));

      await openPanel({ currentUser: ADMIN });
      await screen.findByText('COBOL-Repo synchronisieren');
      const before = vi.mocked(api.getJobs).mock.calls.length;

      fireEvent.click(screen.getByLabelText('Aus dem Job-Center entfernen'));

      await waitFor(() => expect(api.deleteJob).toHaveBeenCalledWith('git', 1));
      // Die Zeile verschwindet aus dem lokalen Zustand -- ein Neuladen würde
      // sie beim naechsten Poll-Takt ohnehin nicht mehr enthalten.
      await waitFor(() => expect(screen.queryByText('COBOL-Repo synchronisieren')).toBeNull());
      expect(vi.mocked(api.getJobs).mock.calls.length).toBe(before);
    });

    it('zeigt die Fehlermeldung des Servers, wenn eine Aktion scheitert', async () => {
      stubJobs([makeJob({ status: 'failed', can_start: true })]);
      vi.mocked(api.startJob).mockRejectedValue(apiError('Job läuft bereits'));

      await openPanel({ currentUser: ADMIN });

      fireEvent.click(await screen.findByText('Neu anstoßen'));

      expect((await screen.findByRole('alert')).textContent).toContain('Job läuft bereits');
    });

    it('fällt ohne Servertext auf eine allgemeine Fehlermeldung zurück', async () => {
      stubJobs([makeJob({ status: 'running', can_stop: true })]);
      vi.mocked(api.stopJob).mockRejectedValue(apiError());

      await openPanel({ currentUser: ADMIN });

      fireEvent.click(await screen.findByText('Stoppen'));

      expect((await screen.findByRole('alert')).textContent).toContain('Job-Aktion konnte nicht ausgeführt werden.');
    });

    it('sperrt den Knopf, solange die Aktion läuft', async () => {
      stubJobs([makeJob({ status: 'failed', can_start: true })]);
      let finish: () => void = () => {};
      vi.mocked(api.startJob).mockReturnValue(new Promise(resolve => { finish = () => resolve(axiosResponse({})); }));

      await openPanel({ currentUser: ADMIN });
      // jest-dom-Matcher stehen im Typecheck nicht zur Verfuegung
      // (vitest.setup.ts ist in tsconfig.json ausgeschlossen), deshalb hier
      // wie im Rest der Suite die einfache Eigenschaftspruefung.
      const button = (await screen.findByText('Neu anstoßen')).closest('button') as HTMLButtonElement;

      fireEvent.click(button);

      await waitFor(() => expect(button.disabled).toBe(true));

      finish();
      await waitFor(() => expect(button.disabled).toBe(false));
    });

    it('verschluckt einen fehlgeschlagenen Poll, statt die Ansicht abstürzen zu lassen', async () => {
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
      vi.mocked(api.getJobs).mockRejectedValue(apiError('kaputt'));

      renderJobCenter();

      await waitFor(() => expect(consoleError).toHaveBeenCalled());
      expect(screen.getByLabelText('Job-Center')).toBeTruthy();
    });

    it('schweigt bei einem 401, weil dann nur die Sitzung abgelaufen ist', async () => {
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
      vi.mocked(api.getJobs).mockRejectedValue(Object.assign(new Error('unauthorized'), { isAxiosError: true, response: { status: 401 } }));

      renderJobCenter();

      await waitFor(() => expect(api.getJobs).toHaveBeenCalled());
      expect(consoleError).not.toHaveBeenCalled();
    });
  });
});
