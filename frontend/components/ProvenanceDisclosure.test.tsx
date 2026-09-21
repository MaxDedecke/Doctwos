import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { ProvenanceDisclosure } from './ProvenanceDisclosure';

describe('ProvenanceDisclosure', () => {
  it('shows an approved document link separately from claim verification', () => {
    render(
      <LanguageProvider>
        <ProvenanceDisclosure
          theme="light"
          provenance={{
            kind: 'document_claim',
            verification_status: 'unverified',
            source_name: 'Payment manual',
            source_type: 'Confluence',
            source_revision: 'revision-123456789',
            revision_kind: 'commit',
            last_synced_at: '2026-09-21T10:00:00Z',
            association_status: 'approved',
            association_reviewed_at: '2026-09-20T10:00:00Z',
            locator: { file_path: 'Payments', page: 4, section: 'Validation' },
          }}
        />
      </LanguageProvider>,
    );

    fireEvent.click(screen.getAllByText(/Dokumentaussage/)[0]);
    expect(screen.getByText('Nicht fachlich verifiziert')).toBeTruthy();
    expect(screen.getByText('Verknüpfung freigegeben')).toBeTruthy();
    expect(screen.getByText('Payment manual · Confluence')).toBeTruthy();
    expect(screen.getByText('Payments · S. 4 · Validation')).toBeTruthy();
  });

  it('renders missing revision and sync time as unavailable instead of implying freshness', () => {
    render(
      <LanguageProvider>
        <ProvenanceDisclosure theme="dark" provenance={{ kind: 'code_fact', verification_status: 'indexed_unreviewed' }} />
      </LanguageProvider>,
    );
    fireEvent.click(screen.getAllByText(/Automatisch analysierter Codefakt/)[0]);
    expect(screen.getAllByText('Nicht verfügbar oder nicht erfasst').length).toBeGreaterThanOrEqual(2);
  });
});
