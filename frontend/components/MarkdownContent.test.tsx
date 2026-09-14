import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

/** Dieselbe {{var}}-Ersetzung wie LanguageContext.tsx::t, mit den zwei
 * analysisStatus-Vorlagen als Mini-Wörterbuch -- genug, um
 * analysisStatus.ts::formatAnalysisStatusTooltip gegen einen realistischen
 * `t()` zu testen, ohne die echten JSON-Wörterbücher zu importieren. */
const FAKE_DICT: Record<string, string> = {
  'analysisStatus.tooltipWithReasons': '{{label}}: {{reasons}}',
};
const fakeT = (key: string, vars?: Record<string, string | number>) => {
  const template = FAKE_DICT[key] ?? key;
  if (!vars) return template;
  return Object.entries(vars).reduce((acc, [k, v]) => acc.replace(`{{${k}}}`, String(v)), template);
};

vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({ t: fakeT }),
}));

import {
  CodeBlock,
  MarkdownContent,
  parseTableAlignment,
  parseText,
  splitTableRow,
  type KnownSource,
} from './MarkdownContent';

/** Rendert nur das, was `parseText` zurückgibt -- die Funktion selbst bleibt eine
 * reine Funktion ohne eigenen Component-Lifecycle, das Rendering dient allein
 * dazu, das erzeugte React-Tree über das DOM zu prüfen. */
function renderParsed(
  text: string,
  onFileClick: (filePath: string, line?: number, sourceId?: string) => void,
  knownSources?: KnownSource[],
  theme = 'dark'
) {
  return render(<>{parseText(text, onFileClick, theme, fakeT, knownSources)}</>);
}

describe('splitTableRow (reine Funktion)', () => {
  it('splits a basic row and trims each cell', () => {
    expect(splitTableRow('| a | b | c |')).toEqual(['a', 'b', 'c']);
    expect(splitTableRow('|  a  |  b  |')).toEqual(['a', 'b']);
  });

  it('works without leading/trailing pipes', () => {
    expect(splitTableRow('a | b')).toEqual(['a', 'b']);
  });

  it('unescapes an escaped pipe inside a cell instead of splitting on it', () => {
    expect(splitTableRow('a\\|b | c')).toEqual(['a|b', 'c']);
  });

  it('does not treat a pipe inside a backtick code span as a delimiter', () => {
    // Regression: a citation like `some|title.pdf` used to lose its closing
    // backtick because the bare pipe inside it was split as a column delimiter.
    expect(splitTableRow('`a|b` | c')).toEqual(['`a|b`', 'c']);
  });
});

describe('parseTableAlignment (reine Funktion)', () => {
  it('maps each separator marker to its alignment', () => {
    expect(parseTableAlignment('| :--- | ---: | :---: | --- |')).toEqual([
      'left', 'right', 'center', undefined,
    ]);
  });
});

describe('parseText — Code-Zitate', () => {
  it('renders a non-file backtick span as inline code, not a citation button', () => {
    const onFileClick = vi.fn();
    renderParsed('`SELECT * FROM X`', onFileClick);

    const code = screen.getByText('SELECT * FROM X');
    expect(code.tagName).toBe('CODE');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('turns a `file.ext:line` citation into a clickable button', () => {
    const onFileClick = vi.fn();
    renderParsed('`DISPATCHER.cbl:120`', onFileClick);

    fireEvent.click(screen.getByText('DISPATCHER.cbl:120'));
    expect(onFileClick).toHaveBeenCalledWith('DISPATCHER.cbl', 120, undefined);
  });

  it('collapses a `file.ext:start-end` range down to its start line', () => {
    const onFileClick = vi.fn();
    renderParsed('`DISPATCHER.cbl:100-150`', onFileClick);

    fireEvent.click(screen.getByText('DISPATCHER.cbl:100-150'));
    expect(onFileClick).toHaveBeenCalledWith('DISPATCHER.cbl', 100, undefined);
  });

  it('shows the code icon for a plain source file, not the document icon', () => {
    renderParsed('`DISPATCHER.cbl`', vi.fn());
    const button = screen.getByRole('button');
    expect(button.querySelector('.lucide-code')).toBeTruthy();
    expect(button.querySelector('.lucide-book-open')).toBeNull();
  });

  it('resolves a bare filename against a known source by basename (path fallback)', () => {
    // Ein Modell zitiert oft nur den Dateinamen statt des vollen Pfads -- das
    // muss trotzdem den echten (verschachtelten) Pfad öffnen, sonst sucht die
    // Oberfläche die Datei fälschlich im Repo-Wurzelverzeichnis.
    const onFileClick = vi.fn();
    const knownSources: KnownSource[] = [{ file: 'src/programs/DISPATCHER.cbl', source_id: 42 }];
    renderParsed('`DISPATCHER.cbl`', onFileClick, knownSources);

    fireEvent.click(screen.getByText('DISPATCHER.cbl'));
    expect(onFileClick).toHaveBeenCalledWith('src/programs/DISPATCHER.cbl', undefined, '42');
  });

  it('resolves an extensionless knowledge-source title exactly, with the document icon', () => {
    const onFileClick = vi.fn();
    const knownSources: KnownSource[] = [{ file: 'Deployment Guide', source_id: 'conf-9' }];
    renderParsed('`Deployment Guide`', onFileClick, knownSources);

    const button = screen.getByRole('button');
    expect(button.querySelector('.lucide-book-open')).toBeTruthy();
    fireEvent.click(button);
    expect(onFileClick).toHaveBeenCalledWith('Deployment Guide', undefined, 'conf-9');
  });

  it('strips a stray `:page` suffix off an extensionless title before matching it', () => {
    const onFileClick = vi.fn();
    const knownSources: KnownSource[] = [{ file: 'Deployment Guide', source_id: 'conf-9' }];
    renderParsed('`Deployment Guide:3`', onFileClick, knownSources);

    fireEvent.click(screen.getByText('Deployment Guide:3'));
    expect(onFileClick).toHaveBeenCalledWith('Deployment Guide', 3, 'conf-9');
  });

  // O-120: eine zitierte Datei, die nicht uneingeschränkt analysiert ist,
  // trägt einen Warn-Punkt + erklärenden Tooltip statt unkommentiert wie
  // jede andere Quelle auszusehen.
  it('marks a citation whose source has a non-complete analysis status', () => {
    const knownSources: KnownSource[] = [
      { file: 'PAYROLL.cbl', analysis_status: 'partial', analysis_reasons: ['mismatched input'] },
    ];
    renderParsed('`PAYROLL.cbl`', vi.fn(), knownSources);

    const button = screen.getByRole('button');
    expect(button.querySelector('[data-testid="analysis-status-dot"]')).toBeTruthy();
    expect(button.getAttribute('title')).toContain('mismatched input');
  });

  it('leaves a citation without a non-complete analysis status unmarked', () => {
    const knownSources: KnownSource[] = [{ file: 'OK.cbl' }];
    renderParsed('`OK.cbl`', vi.fn(), knownSources);

    const button = screen.getByRole('button');
    expect(button.querySelector('[data-testid="analysis-status-dot"]')).toBeNull();
    expect(button.getAttribute('title')).toBeNull();
  });
});

describe('parseText — Zitate ohne Backticks (Tabellenzellen-Fallback)', () => {
  it('recognizes a known source title in plain text and leaves the rest untouched', () => {
    const onFileClick = vi.fn();
    const knownSources: KnownSource[] = [{ file: 'DISPATCHER.cbl', source_id: 5 }];
    const { container } = renderParsed('Siehe DISPATCHER.cbl für Details', onFileClick, knownSources);

    expect(container.textContent).toBe('Siehe DISPATCHER.cbl für Details');
    fireEvent.click(screen.getByText('DISPATCHER.cbl'));
    expect(onFileClick).toHaveBeenCalledWith('DISPATCHER.cbl', undefined, '5');
  });

  it('prefers the longer of two overlapping known titles instead of matching a substring', () => {
    const onFileClick = vi.fn();
    const knownSources: KnownSource[] = [{ file: 'A.cbl' }, { file: 'SUB-A.cbl' }];
    renderParsed('SUB-A.cbl', onFileClick, knownSources);

    // Ein einziger Button für den vollen Titel -- nicht zwei (ein Treffer für
    // "A.cbl" als Teilstring plus liegengebliebener Text "SUB-").
    expect(screen.getAllByRole('button')).toHaveLength(1);
    fireEvent.click(screen.getByText('SUB-A.cbl'));
    expect(onFileClick).toHaveBeenCalledWith('SUB-A.cbl', undefined, undefined);
  });

  it('leaves plain text alone when no known sources are given', () => {
    renderParsed('Siehe DISPATCHER.cbl für Details', vi.fn(), undefined);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('marks a backtick-less citation the same way as a backtick one (O-120)', () => {
    const knownSources: KnownSource[] = [{ file: 'DISPATCHER.cbl', analysis_status: 'skipped', analysis_reasons: [] }];
    renderParsed('Siehe DISPATCHER.cbl für Details', vi.fn(), knownSources);

    const button = screen.getByRole('button');
    expect(button.querySelector('[data-testid="analysis-status-dot"]')).toBeTruthy();
  });
});

describe('parseText — Fettdruck und <br>', () => {
  it('renders **bold** as a strong element', () => {
    renderParsed('Das ist **wichtig**.', vi.fn());
    const strong = screen.getByText('wichtig');
    expect(strong.tagName).toBe('STRONG');
  });

  it('splits a literal <br> tag into a real line break', () => {
    const { container } = renderParsed('Zeile1<br>Zeile2', vi.fn());
    expect(container.querySelectorAll('br')).toHaveLength(1);
    expect(container.textContent).toBe('Zeile1Zeile2');
  });
});

describe('MarkdownContent — Blockstruktur', () => {
  it('renders an ATX heading with its level and keeps citations inside it clickable', () => {
    const onFileClick = vi.fn();
    const knownSources: KnownSource[] = [{ file: 'DISPATCHER.cbl' }];
    render(<MarkdownContent content="## Siehe `DISPATCHER.cbl`" onFileClick={onFileClick} theme="dark" knownSources={knownSources} />);

    const heading = screen.getByRole('heading', { level: 2 });
    fireEvent.click(screen.getByText('DISPATCHER.cbl'));
    expect(heading.textContent).toContain('DISPATCHER.cbl');
    expect(onFileClick).toHaveBeenCalledWith('DISPATCHER.cbl', undefined, undefined);
  });

  it('renders a thematic break as <hr>', () => {
    const { container } = render(<MarkdownContent content={'before\n\n---\n\nafter'} onFileClick={vi.fn()} theme="dark" />);
    expect(container.querySelector('hr')).toBeTruthy();
    expect(container.textContent).toContain('before');
    expect(container.textContent).toContain('after');
  });

  it('groups consecutive blockquote lines into one blockquote', () => {
    const { container } = render(<MarkdownContent content={'> Zeile 1\n> Zeile 2'} onFileClick={vi.fn()} theme="dark" />);
    const blockquotes = container.querySelectorAll('blockquote');
    expect(blockquotes).toHaveLength(1);
    expect(blockquotes[0].textContent).toBe('Zeile 1\nZeile 2');
  });

  it('keeps a paragraph\'s internal line breaks', () => {
    const { container } = render(<MarkdownContent content={'Zeile 1\nZeile 2'} onFileClick={vi.fn()} theme="dark" />);
    const paragraph = container.querySelector('p')!;
    expect(paragraph.textContent).toBe('Zeile 1\nZeile 2');
  });

  it('renders nothing for empty content', () => {
    const { container } = render(<MarkdownContent content="" onFileClick={vi.fn()} theme="dark" />);
    expect(container.innerHTML).toBe('');
  });
});

describe('MarkdownContent — GFM-Tabelle', () => {
  const table = [
    '| Name | Wert |',
    '| :--- | ---: |',
    '| A | 1 |',
    '| B | 2 |',
  ].join('\n');

  it('renders header and body cells with the declared per-column alignment', () => {
    const { container } = render(<MarkdownContent content={table} onFileClick={vi.fn()} theme="dark" />);

    const headers = container.querySelectorAll('th');
    expect(headers).toHaveLength(2);
    expect(headers[0].textContent).toBe('Name');
    expect(headers[0].style.textAlign).toBe('left');
    expect(headers[1].style.textAlign).toBe('right');

    const rows = container.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(2);
    const firstRowCells = rows[0].querySelectorAll('td');
    expect(firstRowCells[0].textContent).toBe('A');
    expect(firstRowCells[0].style.textAlign).toBe('left');
    expect(firstRowCells[1].style.textAlign).toBe('right');
  });

  it('keeps a citation inside a table cell clickable', () => {
    const onFileClick = vi.fn();
    const content = ['| Quelle | Status |', '| --- | --- |', '| `DISPATCHER.cbl:10` | offen |'].join('\n');
    render(<MarkdownContent content={content} onFileClick={onFileClick} theme="dark" />);

    fireEvent.click(screen.getByText('DISPATCHER.cbl:10'));
    expect(onFileClick).toHaveBeenCalledWith('DISPATCHER.cbl', 10, undefined);
  });
});

describe('MarkdownContent — Codeblöcke', () => {
  it('extracts the fenced language and code, surrounded by the normal text blocks', () => {
    const content = "davor\n```python\nprint('hi')\n```\ndanach";
    const { container } = render(<MarkdownContent content={content} onFileClick={vi.fn()} theme="dark" />);

    expect(container.textContent).toContain('davor');
    expect(container.textContent).toContain('danach');
    expect(screen.getByText('python')).toBeTruthy();
    expect(container.querySelector('pre code')!.textContent).toBe("print('hi')\n");
  });

  it('falls back to a generic label when the fence has no language', () => {
    render(<MarkdownContent content={'```\nplain\n```'} onFileClick={vi.fn()} theme="dark" />);
    expect(screen.getByText('code')).toBeTruthy();
  });
});

describe('CodeBlock — Kopieren', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  });

  afterEach(() => {
    Reflect.deleteProperty(navigator, 'clipboard');
  });

  // Bewusst echte Zeit statt vi.useFakeTimers(): Fake-Timer blockieren sich
  // zusammen mit waitFor/findBy* selbst (React/testing-library pollen intern
  // über echte Timer) -- derselbe Befund wie schon bei O-100 (LogsSettingsTab).
  it('shows a confirmation after copying and reverts it after a moment', async () => {
    render(<CodeBlock language="python" code="print('hi')" theme="dark" />);

    fireEvent.click(screen.getByText('common.copy'));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("print('hi')"));
    expect(await screen.findByText('common.copied')).toBeTruthy();

    expect(await screen.findByText('common.copy', {}, { timeout: 2500 })).toBeTruthy();
  }, 4000);
});
