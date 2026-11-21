import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { api } from '@/app/services/api';
import { axiosResponse } from '@/test/http';
import { CitedLinesPreview } from './CitedLinesPreview';

vi.mock('@/lib/i18n/LanguageContext', () => ({ useLanguage: () => ({ t: (key: string) => key, language: 'de' }) }));

describe('CitedLinesPreview', () => {
  it('shows the cited line with numbered context and marks it', async () => {
    const content = Array.from({ length: 12 }, (_, index) => `       LINE-${index + 1}.`).join('\n');
    vi.spyOn(api, 'getKnowledgeSourceContent').mockResolvedValue(axiosResponse({ content, format: 'text' }) as never);

    render(<CitedLinesPreview sourceId={7} path="app/cbl/X.cbl" line={5} />);

    const preview = await screen.findByLabelText('pathCard.preview');
    expect(preview.textContent).toContain('3       LINE-3.');
    expect(preview.textContent).toContain('10       LINE-10.');
    expect(preview.textContent).not.toContain('LINE-11');
    expect(preview.querySelector('.bg-ds-indigo-500\\/10')?.textContent).toContain('LINE-5');
  });
});
