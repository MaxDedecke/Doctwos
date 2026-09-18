import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AgentSteps } from './AgentSteps';

vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({ t: (key: string) => key }),
}));

describe('AgentSteps', () => {
  it('uses the Doctus sans font for a thought instead of the browser serif fallback', () => {
    render(<AgentSteps steps={[{ type: 'thought', content: 'Ich prüfe den Ablauf.' }]} theme="dark" />);

    fireEvent.click(screen.getByRole('button', { name: /agentSteps\.showThoughts/ }));

    expect(screen.getByText('Ich prüfe den Ablauf.').parentElement?.className).toContain('font-sans');
    expect(screen.getByText('Ich prüfe den Ablauf.').parentElement?.className).not.toContain('font-serif');
  });
});
