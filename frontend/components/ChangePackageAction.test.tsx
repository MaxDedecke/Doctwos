import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/app/services/api';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { ChangePackageAction } from './ChangePackageAction';

const PACKAGE = {
  status: 'ok',
  impact_status: 'ok',
  scope: { direction: 'both', hops: 2, truncated: true },
  change_impact: {
    status: 'ok',
    direction: 'both',
    hops: 2,
    truncated: true,
    target: { entity_ids: [1] },
    nodes: [
      { id: 1, name: 'ROOT', qualified_name: 'PAYMENT.ROOT', file_path: 'src/PAYMENT.cbl', source_id: 9 },
      { id: 2, name: 'CALLER', qualified_name: 'PAYMENT.CALLER', file_path: 'src/PAYMENT.cbl', source_id: 9 },
      { id: 3, name: 'CUSTOMER-FILE', qualified_name: 'CUSTOMER-FILE', file_path: 'copy/CUSTOMER.cpy', source_id: 9 },
    ],
    edges: [
      { id: 10, source: 2, target: 1, target_name: 'ROOT', type: 'CALLS', resolution: 'resolved', start_line: 40, end_line: 40 },
      { id: 11, source: 1, target: 3, target_name: 'CUSTOMER-FILE', type: 'READS_FILE', resolution: 'resolved', start_line: 58, end_line: 58 },
    ],
    unknown_edges: [
      { id: 12, source_entity_id: 2, source_name: 'CALLER', file_path: 'src/PAYMENT.cbl', start_line: 65, target_name: 'DYNAMIC-SERVICE', resolution: 'dynamic', type: 'CALL' },
    ],
    impact_summary: { limitations: ['Bounded index graph.'] },
  },
  affected_code: [
    {
      id: 1,
      name: 'ROOT',
      qualified_name: 'PAYMENT.ROOT',
      file_path: 'src/PAYMENT.cbl',
      source_id: 9,
      start_line: 1,
      end_line: 20,
      relationship_path: { root_entity_id: 1, hops: 0, edges: [] },
    },
    {
      id: 2,
      name: 'CALLER',
      qualified_name: 'PAYMENT.CALLER',
      file_path: 'src/PAYMENT.cbl',
      source_id: 9,
      start_line: 30,
      end_line: 70,
      relationship_path: {
        root_entity_id: 1,
        hops: 1,
        edges: [{ edge_id: 10, relationship: 'CALLS', resolution: 'resolved', evidence_file: 'src/PAYMENT.cbl', evidence_start_line: 40, traversed_against_relationship: true }],
      },
    },
  ],
  linked_knowledge: [
    {
      entity_id: 1,
      title: 'Possible payment rule',
      classification: 'possible_domain_rule',
      classification_basis: 'title_or_excerpt_keyword',
      classification_keyword: 'rule',
      source_type: 'Confluence',
      url: 'https://docs.example.test/payment',
      evidence: { status: 'approved', source_id: 12, file_path: 'PAYMENT_RULES', chunk_id: 70, page: 4, section: 'Payment', excerpt: 'Check the payment rule.' },
    },
    {
      entity_id: 1,
      title: 'Payment reference manual',
      classification: 'linked_document',
      classification_basis: 'approved_link_only',
      source_type: 'Confluence',
      url: 'https://docs.example.test/manual',
      evidence: { status: 'approved', source_id: 12, file_path: 'PAYMENT_MANUAL', chunk_id: 71, section: 'Overview', excerpt: 'Reference details.' },
    },
  ],
  historical_issues: [],
  tests: {
    status: 'found',
    items: [{ entity: { id: 50, name: 'test_payment', file_path: 'tests/test_payment.py', source_id: 9, start_line: 8 }, relationship: 'CALLS', evidence: { start_line: 12 } }],
    truncated: false,
    coverage_claim: 'none',
  },
  responsibility: {
    status: 'found',
    items: [{ source_id: 9, owners: ['@payments'], files: ['src/PAYMENT.cbl'], source: { type: 'CODEOWNERS', file_path: 'CODEOWNERS' } }],
    unknown_files: [],
    partial: false,
  },
  evidence_gaps: ['Dynamic calls may be missing.'],
  limitations: ['This is not a complete runtime impact proof.'],
};

function renderAction(onOpenCode = vi.fn(), onOpenDoc = vi.fn()) {
  return render(
    <LanguageProvider>
      <ChangePackageAction
        projectId={7}
        target={{ entityId: 1, label: 'PAYMENT.ROOT' }}
        theme="dark"
        onOpenCode={onOpenCode}
        onOpenDoc={onOpenDoc}
      />
    </LanguageProvider>,
  );
}

describe('ChangePackageAction', () => {
  afterEach(() => vi.restoreAllMocks());

  it('submits a described change to the bounded package API and separates evidence categories', async () => {
    const fetchSpy = vi.spyOn(api, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => PACKAGE,
    } as Response);
    renderAction();

    fireEvent.click(screen.getByRole('button', { name: 'Änderung untersuchen' }));
    fireEvent.change(screen.getByLabelText('Was soll geändert werden?'), {
      target: { value: 'Die Kundenprüfung vor dem Buchen erweitern.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Impact-Paket erstellen' }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    const requestUrl = String(fetchSpy.mock.calls[0][0]);
    expect(requestUrl).toContain('/projects/7/change-package?');
    expect(requestUrl).toContain('entity_id=1');
    expect(requestUrl).toContain('direction=both');
    expect(await screen.findByText('Die Kundenprüfung vor dem Buchen erweitern.', { selector: 'p' })).toBeTruthy();
    expect(screen.getByText('Prozessbeziehungen am Änderungsziel', { exact: false })).toBeTruthy();
    expect(screen.getByText('Direkte Codeabhängigkeiten', { exact: false })).toBeTruthy();
    expect(screen.getByText('Datenzugriffe · 1')).toBeTruthy();
    expect(screen.getByText('Freigegebene Dokumentbelege · 1')).toBeTruthy();
    expect(screen.getByText(/Doctus bestätigt daraus keine Fachregel/)).toBeTruthy();
    expect(screen.getByText(/Dynamic calls may be missing/)).toBeTruthy();
    expect(screen.getByText(/Umfangsgrenzen gekürzt/)).toBeTruthy();
  });

  it('opens the indexed code and document evidence from the package', async () => {
    vi.spyOn(api, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => PACKAGE,
    } as Response);
    const onOpenCode = vi.fn();
    const onOpenDoc = vi.fn();
    renderAction(onOpenCode, onOpenDoc);

    fireEvent.click(screen.getByRole('button', { name: 'Änderung untersuchen' }));
    fireEvent.change(screen.getByLabelText('Was soll geändert werden?'), { target: { value: 'Kundenprüfung ändern' } });
    fireEvent.click(screen.getByRole('button', { name: 'Impact-Paket erstellen' }));

    fireEvent.click(await screen.findByRole('button', { name: 'src/PAYMENT.cbl:1' }));
    expect(onOpenCode).toHaveBeenCalledWith('src/PAYMENT.cbl', 1, 9);

    fireEvent.click(screen.getByRole('button', { name: 'Änderung untersuchen' }));
    fireEvent.change(screen.getByLabelText('Was soll geändert werden?'), { target: { value: 'Kundenprüfung ändern' } });
    fireEvent.click(screen.getByRole('button', { name: 'Impact-Paket erstellen' }));
    const documentCard = (await screen.findByText('Payment reference manual')).closest('article');
    expect(documentCard).toBeTruthy();
    fireEvent.click(within(documentCard as HTMLElement).getByRole('button', { name: 'Beleg öffnen' }));
    expect(onOpenDoc).toHaveBeenCalledWith('PAYMENT_MANUAL', 12, expect.objectContaining({ chunkId: 71, section: 'Overview' }));
  });
});
